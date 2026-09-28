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
	bool bDerelict = false;              // a dead station or hulk to investigate: no power, tumbling slowly
	bool bPiloted = false;               // the Captain flies it (first person): no AI, the stick drives it
	float SpinDeg = 0.f;
	// tactical orders by datalink (the Mandate commander's to their ships, the Captain's requests to the fleet)
	int32 OrderTarget = -1;              // ship id to concentrate on (-1: the nearest)
	uint8 Stance = 0;                    // 0 standard, 1 close, 2 standoff, 3 flank, 4 screen (the fleet: cover the Aquila)
	bool bSalvo = false;                 // empty the cells at the next chance (all together: saturate point defence)
	bool bConserve = false;              // fire missiles sparingly

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
	TArray<FString> LostCrew;             // who was flying the aircraft lost since the last report
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

/** The Captain at the stick of a Falcon: what the pilot does this frame (the fighter pawn fills it). */
struct FAstraPilotInput
{
	float Throttle = 0.f;                        // 0..1, the lever
	FVector Strafe = FVector::ZeroVector;        // y lateral, z vertical (-1..1)
	float Roll = 0.f, Pitch = 0.f, Yaw = 0.f;    // stick rates (-1..1)
	bool bBoost = false;
	bool bGuns = false;
	bool bMissile = false;                       // held: one missile at the lock per press
	bool bDecoy = false;                         // held: one decoy salvo per press
};

/** What the Falcon's displays show (world positions in cm for the head-up display). */
struct FAstraPilotStatus
{
	bool bFlying = false;
	bool bDown = false;                          // shot down: the Captain ejected
	float SpeedMps = 0.f, Throttle = 0.f, HullPct = 100.f, ShieldPct = 100.f;
	int32 Missiles = 0;
	int32 Decoys = 0;
	FString LockName;
	float LockProgress = 0.f;                    // 0..1 (1 = locked)
	float LockRangeKm = 0.f;
	FVector LockWorld = FVector::ZeroVector, LeadWorld = FVector::ZeroVector;
	bool bHasLock = false;
	FVector HomeWorld = FVector::ZeroVector;     // the Aquila's recovery tube (Alpha's, port)
	float HomeRangeKm = 0.f;
	bool bCanLand = false;
	int32 Incoming = 0;                          // missiles homing on the Falcon
	TArray<FVector> Hostiles, Friends;           // within 25 km
	TArray<float> HostileSizes;                  // their radius (m): craft or warship
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
/** A place to investigate (a silent station, a drifting hulk): what the crew learns, stage by stage, and what may be
 *  waiting there cold. */
USTRUCT()
struct FAstraPOI
{
	GENERATED_BODY()

	int32 ShipId = -1;
	FString Name;
	TArray<FString> Findings;   // 1: the active scan; 2: a flight group reaches it or the Aquila closes to 5 km; 3: alongside (2 km)
	int32 Revealed = 0;
	float NextRevealT = 0.f;
	TArray<int32> Ambush;       // ships lying cold nearby
	float AmbushKm = 0.f;
	bool bAmbushSprung = false;
	bool bDone = false;
};

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

/** A Janus transit in progress: the helm flies to the gate's approach lane, then the lane field has the ship. */
enum class EAstraGateRun : uint8
{
	None,
	Approach,
	Lane
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

	/** The Mandate's picture of the Aquila (M2): they can engage her only while they hold a track — one of their ships
	 *  inside her signature (EMCON, the drive, radiators out, a coolant plume, a hot hull), or she fired or pinged in the
	 *  last 45 s; a lost track lingers 60 s (dead reckoning), then they search her last known position. */
	float PlayerSignatureKm() const;
	bool IsPlayerTracked() const { return bPlayerTracked; }
	bool PlayerHail(const FString& ContactId, FString& OutDetail);
	bool PlayerCeaseFire(FString& OutDetail);
	/** Flight Control: launch (or re-task an airborne) flight group on a mission; recall it to the flight deck. */
	bool LaunchSquadron(const FString& Name, const FString& Mission, const FString& ContactId, FString& OutDetail);
	bool RecallSquadron(const FString& Name, FString& OutDetail);
	/** How many aircraft of each of our flight groups are on the flight deck (for the hangar's parked craft). */
	void GetDeckState(TMap<FString, int32>& Out) const;
	/** Status line per flight group, for the crew's telemetry and the screens. */
	TSharedRef<FJsonObject> SquadronsJson() const;
	/** The Aquila's weapons as fire control reports them (live: assignments, volleys left, VLS cycle, ammunition). */
	TSharedRef<FJsonObject> PlayerWeaponsJson() const;
	/** Everything the tactical plot should draw right now. */
	void GetHoloBlips(TArray<FAstraHoloBlip>& Out) const;
	/** A Mandate commander's decision (from their mind): continue_attack | hold_fire | withdraw | accept_surrender.
	 *  The senior surviving commander orders the whole strike group; any other captain only their own ship. */
	bool EnemyOrder(const FString& Order, const FString& Reason, const FString& Commander, FString& OutDetail);
	/** The senior Mandate commander's tactical orders (from their mind, by datalink): focus of fire (focus), stance
	 *  (standard | close | standoff | flank | screen), missiles (normal | salvo | conserve), fighters (launch | hold),
	 *  optionally only some ships. What the Aquila's sensors can see of it is reported to the bridge. */
	bool EnemyTactics(const TSharedPtr<FJsonObject>& Args, FString& OutDetail);
	/** The Captain's request to the friendly warships in company (by fleet datalink): focus_fire (target), engage_freely,
	 *  cover_us, close_in, stand_off, hold_fire. Ship: a contact id or "all". */
	bool FleetRequest(const FString& Ship, const FString& Request, const FString& Target, FString& OutDetail);
	/** The Captain takes a Falcon of Alpha from the flight deck (one fewer on deck) or brings it back. */
	bool TakeFalcon();
	void ReturnFalcon();
	/** The Captain's Falcon clears the bow tube: from now on the battle flies it with the pilot's input and moves the pawn
	 *  with the rest of the world (the same frame as every ship). World pose where it leaves the tube, speed relative
	 *  to the Aquila. */
	bool LaunchPiloted(AActor* Pawn, const FVector& WorldPos, const FQuat& WorldRot, float SpeedMps, bool bFromPlanet = false);
	/** The Captain's Falcon leaves the fleet's plot for New Ravenna's atmosphere (it stays the Captain's, off the plot). */
	void LeavePiloted();
	/** The Captain's Falcon was lost down on the planet (one Falcon fewer in Alpha). */
	void FalconLostPlanetside();
	void SetPilotInput(const FAstraPilotInput& In) { Pilot = In; }
	void GetPilotStatus(FAstraPilotStatus& Out) const;
	/** Recovered through the bow tube (bLanded) or the pod picked up after an ejection: the craft leaves the battle. */
	void EndPiloted(bool bLanded);
	bool IsPiloting() const { return PilotedId >= 0; }
	/** Where the Captain is, for the crew: flying (with range and state) or "" when aboard. */
	FString PilotSummary() const;
	/** Bridge world (cm) -> system frame (m), and back for rotations. */
	FVector FromWorld(const FVector& WorldCm) const;
	/** The Aquila's end (the ship subsystem's timing): explosions running along her hull (world bounds), then the
	 *  reactor's breach at ReactorW (world): the flash, the ring, the debris; she is dead from then on. */
	void AquilaBlasts(const FVector& HullCentreW, const FVector& HullExtentW);
	/** After the loss, when the story moves on (hours, days): the fight stops where it was, no more reports. */
	void Freeze() { bFrozen = true; }
	/** The warships still in the system on one side ("ASN Praetorian (battleship), ..."), the Aquila left out. */
	FString ForcesLine(bool bAstra) const;
	void AquilaBreach(const FVector& ReactorW);
	/** Contact id of the ship whose captain commands the Mandate forces now: the group leader, else the biggest ship left. */
	FString MandateCommander() const;
	/** The war director's next beat (from the mind): raid | distress | reinforcements | resupply | calm. Contact ids are
	 *  assigned now (so the mind can give the new commanders a persona before they arrive). */
	bool StartBeat(const TSharedPtr<FJsonObject>& Beat, FString& OutDetail);
	/** Janus transit, on the Captain's order (helm) or Fleet's: the helm flies at full ahead to the gate's approach lane;
	 *  inside the lane the gate's field takes the ship and draws her through the ring into the destination system.
	 *  Args: system_name (+ star_class, planet_type, planet_name when the director charts a new system). */
	bool BeginGateRun(const TSharedPtr<FJsonObject>& Args, FString& OutDetail);
	void AbortGateRun();
	bool IsGateRunActive() const { return GateRun != EAstraGateRun::None; }
	bool IsInLane() const { return GateRun == EAstraGateRun::Lane; }
	/** Where the system's Janus Gate is, Fleet's orders, the transit under way (for the crew and the screens). */
	FString GateStatus() const;
	/** The system the gate is tuned to: the run under way, else Fleet's orders ("" = none). */
	FString GetGateDestination() const { return GateRun != EAstraGateRun::None ? GateDest : FleetOrderedDest; }
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

	/** The campaign: nothing moves until the Captain chooses (new campaign, or continue a saved one). */
	void StartCampaign() { bStarted = true; }
	bool IsStarted() const { return bStarted; }
	/** What a save keeps of the battle side: the Aquila's hull and magazines, her flight groups. */
	TSharedRef<FJsonObject> SaveJson() const;
	/** Continue a saved campaign: the opening scenario is gone, the Aquila is on patrol in the saved system. */
	void ResumeFrom(const TSharedPtr<FJsonObject>& Save);

	/** For the score: is a fight on, how many enemy warships fight within a range, since when the last one ended. */
	bool IsEngaged() const { return bEngagementActive; }
	int32 HostilesFighting(double WithinKm) const;
	float SecondsSinceEngagement() const { return EngagementEndedAt < 0.f ? 1e9f : Time - EngagementEndedAt; }
	/** The Janus lane: seconds left to the crossing (-1 when not in the lane). */
	float LaneSecondsLeft() const { return GateRun == EAstraGateRun::Lane ? (float)(LaneDur - LaneT) : -1.f; }

	/** Camera shake request for the bridge (0..1), decays over time. */
	float ConsumeShake(float DeltaTime);

private:
	bool bFrozen = false;   // Freeze(): the story has left this fight behind
	UPROPERTY() TArray<FAstraBattleShip> Ships;
	UPROPERTY() TArray<FAstraProjectile> Projectiles;
	UPROPERTY() TArray<FAstraFlash> Flashes;
	UPROPERTY() TArray<FAstraSquadron> Squadrons;
	UPROPERTY() TArray<FAstraWreck> Wrecks;
	UPROPERTY() TArray<FAstraWreck> Landmarks;   // the Janus Gate and other fixed structures of the system (Life -1)
	UPROPERTY() TArray<FAstraPOI> POIs;
	void TickPOIs(float Dt);
	void RevealPOI(FAstraPOI& Poi);
	UPROPERTY() TObjectPtr<UStaticMesh> RingMesh;
	UPROPERTY() TObjectPtr<UMaterialInterface> BlastMat;
	UPROPERTY() TObjectPtr<UStaticMesh> CubeMesh;
	bool bBriefed = false;
	bool bStarted = false;              // the campaign has begun (menu choice)
	bool bEngagementActive = false;     // a fight is on: the outcome is evaluated
	float EngagementEndedAt = -1.f;
	float TruceSince = -1.f;            // every hostile holds fire since then (a truce, not yet peace)
	int32 NextContact = 40;             // contact ids for ships the director brings in
	TArray<TPair<float, TSharedPtr<FJsonObject>>> PendingBeats;
	float RepairUntil = -1.f, RepairHullPerSec = 0.f;
	int32 RepairMissiles = 0;
	float CalmUntil = -1.f;
	TSharedPtr<FJsonObject> TransitBeat; // the destination of the Janus transit under way (system name and look)
	EAstraGateRun GateRun = EAstraGateRun::None;
	int32 GateLandmark = INDEX_NONE;    // the system's Janus Gate in Landmarks
	float GateSide = 1.f;               // the face of the ring we approach (+1 = along the gate's axis)
	float GateSteerT = 0.f;
	FString GateDest;                   // destination of the run under way
	FString FleetOrderedDest;           // Fleet orders a transit (the director); the Captain decides when to go
	double LaneT = 0.0, LaneDur = 20.0, LaneK = 0.4;   // the lane: time, duration, initial speed share of the ease
	FVector LaneP0 = FVector::ZeroVector, LaneT0 = FVector::ZeroVector, LaneP1 = FVector::ZeroVector, LaneT1 = FVector::ZeroVector;
	bool bLaneSound = false, bLaneFade = false;
	float GateHeat = 0.f;               // the ring's glow after a transit (1 = just came through), fading
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> GateGlyphMID;
	// the approach lane's markers on both faces of the ring: hoops of light every 2.5 km, a wave running into the gate
	UPROPERTY() TArray<TObjectPtr<UMaterialInstanceDynamic>> LaneRingMIDs;
	TArray<int32> LaneRingIdx;          // in Landmarks
	TArray<float> LaneRingAxial;        // signed distance from the ring along the gate's axis (m)
	void TickGateRun(float Dt);
	void SpawnGate(const FVector& Pos, const FQuat& Att);
	/** Everything but the Aquila leaves the plot (a transit, a resumed campaign). */
	void ClearSystem();
	void DoTransit(const TSharedPtr<FJsonObject>& Beat);
	void ArriveBeat(const TSharedPtr<FJsonObject>& Beat);
	int32 SpawnClass(const FString& Class, const FString& Contact, const FString& Name, const FVector& Pos, float HeadingDeg);
	UPROPERTY() TObjectPtr<UStaticMesh> SphereMesh;
	UPROPERTY() TObjectPtr<UStaticMesh> CylinderMesh;
	UPROPERTY() TObjectPtr<UMaterialInterface> GlowMat;
	UPROPERTY() TObjectPtr<UMaterialInterface> FlareMat;   // soft glow ball (drive flares)
	UPROPERTY() TObjectPtr<UMaterialInterface> ShellMat;

	/** The bridge's position in the Aquila's hull frame (m): the world origin is the bridge, not the ship centre. */
	FVector BridgeOffset = FVector(172.0, 0.0, 62.0);

	float Time = 0.f;
	bool bPlayerTracked = true;
	bool bPlayerEverTracked = false;   // since hostiles appeared: "lost" needs a track first
	float PlayerTrackT = 0.f;
	float PlayerSinceFired = 999.f;
	FVector PlayerLastKnown = FVector::ZeroVector;
	void TickDetection(float Dt);
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
	// --- the Captain's Falcon
	int32 PilotedId = -1;
	FAstraPilotInput Pilot;
	TWeakObjectPtr<AActor> PilotActor;   // the pawn, moved with the craft
	float PilotGunT = 0.f;
	bool bPilotGunSide = false;
	int32 PilotLock = -1;
	float PilotLockT = 0.f;
	bool bPilotMissileLatch = false;
	bool bPilotDecoyLatch = false;
	int32 PilotDecoys = 4;
	bool bPilotDown = false;
	void TickPiloted(FAstraBattleShip& S, float Dt);
	void FirePilotGuns(FAstraBattleShip& S);
	FVector PilotMouth() const;           // Alpha's tube mouth, system frame

	FAstraBattleShip* FindByContact(const FString& Contact);
	FAstraBattleShip* FindById(int32 Id);
	const FAstraBattleShip* FindByContact(const FString& Contact) const { return const_cast<UAstraBattleSubsystem*>(this)->FindByContact(Contact); }
	const FAstraBattleShip* FindById(int32 Id) const { return const_cast<UAstraBattleSubsystem*>(this)->FindById(Id); }
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
