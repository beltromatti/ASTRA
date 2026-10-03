// ASTRA — the world outside the hull: ships of every side, their manoeuvres and weapons, projectiles, damage, the
// opening scenario. Simulated in the Aurelia system frame (metres, doubles) and drawn around the Aquila, which stays
// at the world origin (the bridge is the origin; the universe moves).

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "Dom/JsonObject.h"
#include "AstraWarStats.h"
#include "AstraWarTypes.h"
#include "AstraWarAI.h"
#include "AstraBattleSubsystem.generated.h"

class AStaticMeshActor;
class UMaterialInstanceDynamic;
class UPointLightComponent;
class UStaticMesh;
class USoundBase;
class UAstraWarFX;
class UAstraWarDraw;
class FAstraShipInterior;            // FLOTTA-VIVA: the inside of a ship that is not the Aquila (AstraFleetInterior.h)
struct FAstraFleetView;
struct FAstraHullHit;
class UPrimitiveComponent;
struct FAstraWarFXTest;
enum class EAstraFxFlash : uint8;
enum class EAstraFxShot : uint8;

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

/** Which side an AI thinks for: the index of the side in the books (0 ASTRA, 1 Mandate); -1 for the rest. */
inline int32 AstraSideIdx(EAstraSide S)
{
	return S == EAstraSide::Astra ? 0 : (S == EAstraSide::Mandate ? 1 : -1);
}

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
	// what the Aquila (and her friends, by datalink) knows of a Mandate ship: the track is live, the rest is kept
	uint8 Track = 2;                     // 0 not on our plot, 1 a passive bearing only (no range), 2 a firm track
	bool bClassified = true;             // its class is known
	float TrackHold = 0.f;               // a lost track lingers this long before it degrades
	bool bFog = false;                   // under the fog of war (the director's Mandate ships; the opening's are scripted)
	bool bDark = false;                  // running dark (EMCON): a fraction of its signature, until it lights up
	float LitT = 0.f;                    // it fired: every sensor saw it, for a while
	bool bJamming = false;               // a Mandate capital ship blinding our radar along its bearing (until burn-through)
	bool bGhost = false;                 // a Mandate decoy emitter: a drone faking a warship's drive (a bearing, never a track)
	FVector GhostGoal = FVector::ZeroVector;   // where the decoy flies (its false bearing); zero once it is there
	float GhostLife = 0.f;
	uint8 EwMode = 0;                    // Mandate capital ships: 0 jam once found, 1 jam now, 2 quiet (no jamming, back to dark)
	int32 Decoys = 0;                    // decoy emitters aboard (a Mandate capital ship of a raid carries four)
	bool bIlluminated = false;           // the ASTRA radar paints it (its warning receivers know)
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

	// what the plot's contact list says of it, kept while the state that decides it is the same (a list of hundreds is read every frame)
	mutable FString CvLabel, CvClass;
	mutable uint8 CvKey = 255;
	UPROPERTY() TObjectPtr<AStaticMeshActor> Actor = nullptr;
	// how the war draws it (AstraWarDraw.cpp): a craft with DrawKind >= 0 is an instance of that kind of hull and has no actor; bDrawLamps: its running lights
	// are instances of the lamp set LampSet (and it has no running-light component)
	int16 DrawKind = -1;
	int16 LampSet = -1;
	bool bDrawLamps = false;
	UPROPERTY() TObjectPtr<AStaticMeshActor> ShieldBubble = nullptr;
	UPROPERTY() TObjectPtr<AStaticMeshActor> DriveFlare = nullptr;   // engine plume, kept visible at long range
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> ShieldMID = nullptr;
	float ShieldFlash = 0.f;
	FVector ShieldFacing = FVector::ZeroVector;   // reinforced sector in the ship's frame (zero = balanced)
	float ShieldPower = 1.f;                       // power factor (the player's allocation and damage)
	float WeaponPower = 1.f;
	/** FLOTTA-VIVA (docs/FLOTTA-VIVA.md): the inside of a warship that is not the Aquila: its class's plan, its crew, the Aquila's damage model run on them. Made at the first
	 *  blow that gets through the plating (none before it, none for the Aquila: she has her own); null when the class has no plan or the switch (astra.fleet.interior) is off.
	 *  What it says goes back into the fields above (ShieldPower, WeaponPower) and into the engines', sensors' and hangar's factors; what burns and vents sets the war's sections' flags. */
	TSharedPtr<FAstraShipInterior> Interior;
	float FleetNewsT = -100.f;                     // when its interior last told the war something (the war is told at most so often)
	// --- the physical model of a warship (AstraWarDamage.cpp): its class, shield sectors, armour plates, structure by
	// section, subsystems and weapon mounts with their fields of fire. Hull and Shield above stay the sums (what the rest of
	// the game reads); craft and decoys have no model (Dmg.bModel false) and keep the lumps.
	FName ClassKey;
	AstraWar::FHullBox Box;              // the hull as a shot strikes it (a box from the class's true measures); empty: a sphere of Radius
	uint8 SizeTier = 0;                  // how big it counts (3 capital ship, 2 cruiser, 1 destroyer, 0 smaller): what depends on class size
	FAstraShipDamage Dmg;
	TArray<FAstraMount> Mounts;
	bool bDisabled = false;              // no power: dead in the water, drifting, a derelict (boardable in F5)
	bool bHoldStation = false;           // bench: kept exactly where it is (a target dummy)
	bool bFixedAtt = false;              // bench: and pointed where it is
	// --- the AI's state (AstraWarShipAI.cpp, AstraWarGroups.cpp, AstraWarCraft.cpp, AstraWarKnowledge.cpp)
	int32 GroupId = -1;                  // its battle group (warships)
	int32 FlightId = -1;                 // its flight (craft)
	EAstraTask Task = EAstraTask::Formation;
	FVector TaskPos = FVector::ZeroVector;     // where its group wants it: a slot, a flank point
	FVector TaskVel = FVector::ZeroVector;     // and what that point is doing (feed-forward)
	bool bTaskSet = false;
	float ThinkAcc = 0.f;                // time since it last thought
	FVector Steer = FVector::ZeroVector;       // the velocity it wants (system frame)
	FVector FaceWant = FVector::ZeroVector;    // the heading it wants (unit; zero: along its velocity)
	float RetargetT = 0.f;
	float SeenT[2] = {-1.0e9f, -1.0e9f};       // when each side last held it on its sensors (0 ASTRA, 1 Mandate)
	FVector SeenPos[2] = {FVector::ZeroVector, FVector::ZeroVector};
	FVector SeenVel[2] = {FVector::ZeroVector, FVector::ZeroVector};
	float DeadT = 0.f;                   // craft: seconds since it left the plot (it is cleared from the array after a while)
	bool bHoldMissiles = false;          // its group keeps the cells for a saturating salvo
	float SalvoAt = -1.f;                // launch the salvo at this battle time (timed by the group)
	float CombatValue = 1.f;             // what it is worth in a fight (from its class)
	// craft flight (AstraWarCraft.cpp)
	float Speed = 0.f;                   // along its heading
	uint8 CraftState = 0;                // 0 fighting/flying the mission, 1 breaking (a defensive turn), 2 extending, 3 run in, 4 egress
	float StateT = 0.f;
	FVector BreakDir = FVector::ZeroVector;
	int32 CraftTarget = -1;              // the ship or craft it is going for now
	int32 CraftSlot = 0;                 // its place in the flight (0 the leader)
	float GunHeat = 0.f;                 // guns: seconds until it may fire again
	float SensorKm = 45.f;               // reach of its own sensors at full health
	float LaserDamage = 18.f, LaserCd = 5.f, LaserRange = 4000.f;
	EAstraFate DeathHow = EAstraFate::Alive;
	// the Captain's wing and its radio (AstraWarCraft.cpp, docs/VOLO.md): a craft that flies his wing has a name on the flight net, and what happens to it is told
	FString Radio;                       // "Eagle 2" (empty: an ordinary craft, told only in its squadron's reports)
	int32 LastHitBy = -1;                // the craft or ship whose blow struck it last: a kill is credited to them
	int32 RadioHullStep = 0;             // how far its hull has been called on the radio (0 sound, 1 under 70 %, 2 under 35 %)
	int32 RadioTarget = -1;              // the bandit it last called as engaged
	float RadioT = -100.f;               // when it last called an engagement
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
	EAstraHitKind HitKind = EAstraHitKind::Missile;   // what it does on impact (the damage type follows)
	int8 OwnerSide = -1;                 // the side that fired it (0 ASTRA, 1 Mandate)
	bool bDecoyChecked = false;          // a missile coming at the Aquila meets her decoys once, on its terminal run
	int32 FxSlot = -1;                   // what the visual effects keep of it (its trail, where it was drawn from): UAstraWarFX
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
	float EngagedAt = -100.f;              // when one of its flights last met the enemy (told as `flight: alpha squadron engaged ...`, at most once in 45 s)
	bool bAirborneReported = false;
	int32 Launched = 0;      // aircraft launched in this sortie
	int32 TorpedoesAway = 0; // released since the last report (one spoken report per torpedo run)
	float TorpedoReportAt = -1.f;
	FString TorpedoTarget;
	EAstraSide Side = EAstraSide::Astra;   // Mandate wings fly from their cruisers
	int32 CarrierId = -1;                  // the ship they launch from and land on
	int32 Rockets = 0;                     // per aircraft (Mandate strike fighters)
	bool bAuto = false;                    // its craft pick their own targets (the Mandate's wings, a bench scenario's): no crew to task it
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
	bool bCanRecover = false;                    // within the deck's recovery guidance's reach: F (or the flight controller) and it flies her in
	bool bRecovering = false;                    // the guidance has her: clear of the hull, the gate in front of the bow, down the tube's axis
	bool bRecovered = false;                     // at the mouth, slow: into the tube
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
	bool bBearingOnly = false;              // a passive bearing, no range: drawn at the rim along the bearing
	bool bJamming = false;                  // its jamming strobe: a flickering line from the Aquila along its bearing
	bool bRetreating = false;
	bool bHoldFire = false;
	bool bTargeted = false;                 // our fire control is on it
	bool bCraft = false;                    // fighter / bomber / drone
	bool bNoLabel = false;                  // only a flight group's leader is labelled
	bool bFiringAtUs = false;               // its guns or its commander's orders are on the Aquila
	int32 Id = -1;                          // the ship's id (the battle's; the plot's own tags and groupings are made from these)
	int32 Squadron = -1;                    // a craft's flight group (index in the battle's squadrons)
	float Size = 1.f;                       // 1 capital, ~0.7 escort, ~0.55 small
	float Fade = 1.f;
	float RangeKm = 0.f;
	FString Name;
	FString Contact;
	FString ClassShort;                     // classified but not identified: "Acheron class"
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
	float Radius = 0.f;                   // a hulk (Life -1) is an obstacle of this size for the ships that steer round it
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

	friend class UAstraWarFX;            // the war's visual effects read the battle's state (AstraWarFX*.cpp)
	friend class UAstraWarDraw;          // and so does the instanced drawing of its craft and lamps (AstraWarDraw.cpp)
	friend struct FAstraWarFXTest;       // and the console that tries them (astra.fx.*)

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
	/** The deck's recovery guidance takes the Captain's Falcon (an automatic carrier landing): out of the way of the hull, to the approach gate
	 *  in front of the bow, down the tube's axis to its mouth. False when she is out of its reach (or not flying). By: who asked, for the report. */
	bool StartPilotRecovery(const FString& By);
	/** The Captain takes the stick back (or the guidance is no longer wanted). */
	void StopPilotRecovery(const FString& Why);
	bool IsPilotRecovering() const { return bPilotAuto; }
	/** The opening's own script for the strike group, the vanguard and the relief (stages 2-3), or the March playing them (CAMPAGNA): false when
	 *  the strike group is already in. */
	bool SetOpeningScript(bool bScript, FString& OutDetail);
	bool IsPiloting() const { return PilotedId >= 0; }
	int32 GetPilotedId() const { return PilotedId; }
	/** Where the Captain is, for the crew: flying (with range and state) or "" when aboard. */
	FString PilotSummary() const;
	/** Bridge world (cm) -> system frame (m), and back for rotations. */
	FVector FromWorld(const FVector& WorldCm) const;
	/** The Aquila's end (the ship subsystem's timing): explosions running along her hull (world bounds), then the
	 *  reactor's breach at ReactorW (world): the flash, the ring, the debris; she is dead from then on. */
	void AquilaBlasts(const FVector& HullCentreW, const FVector& HullExtentW);
	/** After the loss, when the story moves on (hours, days): the fight stops where it was, no more reports. */
	void Freeze() { bFrozen = true; }
	/** The main viewscreen tells the drawing that its camera is zoomed far out on a target: our own craft nearer than WithinKm to the Aquila would cross its lens
	 *  as huge blurred shapes, so they are drawn in a set the camera is told to leave out (ExemptId, the craft it is showing, is not). */
	void SetLensHint(bool bActive, double WithinKm, int32 ExemptId);
	void GetNearLensComponents(TArray<UPrimitiveComponent*>& Out) const;
	/** What the instanced drawing of the craft and the lamps holds and costs (astra.war.stat), as text and as JSON for the bench's record. */
	FString DrawStats() const;
	TSharedRef<FJsonObject> DrawStatsJson() const;
	/** Battle scars: a burn (and, for a heavy hit, a breach) painted where a hit landed on a hull; hot at first, cooling. */
	struct FAstraScar
	{
		TWeakObjectPtr<class UDecalComponent> Decal;
		TWeakObjectPtr<class UMaterialInstanceDynamic> Mid;
		TWeakObjectPtr<AActor> On;
		float Heat = 1.f;
		float Shown = 1.f;
	};
	TArray<FAstraScar> Scars;
	void AddScar(const FAstraBattleShip& S, const FVector& SystemHit, float Damage);
	void TickScars(float Dt);
	/** The Aquila's decoys (two flares and chaff canisters a launch, eight aboard): for 18 s each missile on its
	 *  terminal run at her may be drawn off. */
	bool LaunchDecoys(FString& OutDetail);
	int32 PlayerDecoys = 8;
	float DecoyT = 0.f;
	int32 DecoysSeduced = 0;
	float LastDecoyReport = -100.f;
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
	/** How far the Aquila is from the system's Janus Gate (km), or -1 when there is none (TELETRASPORTO: no beam crosses a Gate's field). */
	double GateDistanceKm() const;
	/** The system the gate is tuned to: the run under way, else Fleet's orders ("" = none). */
	FString GetGateDestination() const { return GateRun != EAstraGateRun::None ? GateDest : FleetOrderedDest; }
	/** Where a live contact is from the Aquila, aimed at its lead point (for the helm's intercept). */
	bool ContactGeometry(const FString& ContactId, double& OutBearing, double& OutMark, double& OutRangeKm) const;
	void SetPlayerShields(bool bUp) { if (Ships.Num()) { Ships[0].bShieldsUp = bUp; } }
	/** Structure damage from inside (fires): hull points, no shields. */
	void PlayerInternalDamage(float Hull) { if (Ships.Num()) { AddHullDelta(Ships[0], -Hull); } }

	float PlayerHullFraction() const { return Ships.Num() ? Ships[0].Hull / Ships[0].HullMax : 1.f; }
	/** Weapon reach as the plot may show it (km; 0 = none or unknown). */
	struct FWeaponRanges
	{
		float RailKm = 0.f, LaserKm = 0.f, MissileKm = 0.f, PointDefenseKm = 0.f;
	};
	/** Empty id: the Aquila's own weapons. A contact id: that ship's reach as the Aquila knows it: its class's weapons once
	 *  it is classified (fog of war), all zeros before. The numbers are the ones the fire code uses (the class table, or
	 *  what a scenario set on the ship). (AstraBattleQueries.cpp) */
	FWeaponRanges GetWeaponRanges(const FString& ContactId = FString()) const;
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
	/** One ship as the Aquila knows it now (fog of war applied): what the stations' executors and the main viewscreen use.
	 *  (AstraBattleQueries.cpp) */
	struct FContactView
	{
		int32 Id = -1;
		FString ContactId;
		FString Label;             // what the crew may call it: the name once identified, the class once classified, else the id
		FString Class;             // empty until classified
		EAstraSide Side = EAstraSide::Neutral;
		uint8 Track = 0;           // 1 a bearing only (no range), 2 a firm track
		bool bCraft = false;       // fighters, bombers, drones
		bool bCapital = false;     // a warship (not a craft, a hulk or a freighter)
		bool bFleeing = false;
		bool bFiringAtUs = false;  // its guns or its commander's orders are on the Aquila
		bool bDerelict = false;
		bool bJamming = false;
		bool bUnknown = false;     // not classified yet (or running cold) and not shown hostile: of no known side
		FVector Pos = FVector::ZeroVector;   // m, system frame (bearing-only: somewhere along the bearing)
		FVector Vel = FVector::ZeroVector;   // m/s (zero when unknown)
		double RangeKm = -1.0;               // -1 unknown
		double BearingDeg = 0.0, MarkDeg = 0.0;
		float HullFrac = -1.f, ShieldFrac = -1.f;   // -1 unknown
		float RadiusM = 100.f;
		const AStaticMeshActor* Actor = nullptr;   // what the optical sensors see of it (firm tracks only)
		AStaticMeshActor* Flare = nullptr;         // its drive plume, sized to be seen from the bridge (not through a zoom)
	};
	/** Every contact on the Aquila's plot (not the Aquila herself), nearest first: a copy of the shared list below, for a caller that keeps or changes its own. */
	void GetContacts(TArray<FContactView>& Out) const;
	/** The plot as the Aquila knows it, built once for each step of the battle and shared by everyone who reads it within that step (a dozen readers a frame: the stations'
	 *  executors, the screens, the holo table, the main viewscreen, the HUDs; with two hundred contacts each used to make its own list). The references hold until the
	 *  battle's next tick: never keep one. (AstraBattleQueries.cpp, AstraBattleSubsystem.cpp) */
	const TArray<FContactView>& Contacts() const;
	/** What the tactical plot draws (ships, craft, missiles, blasts), shared in the same way. */
	const TArray<FAstraHoloBlip>& HoloBlips() const;
	/** What the plot holds, counted when its lists are made: the screens' headlines (ships by side, craft by side, missiles in flight). */
	struct FPlotCounts
	{
		int32 HostileShips = 0, FriendlyShips = 0, HostileCraft = 0, FriendlyCraft = 0, Missiles = 0;
	};
	const FPlotCounts& PlotCounts() const;
	/** What the shared lists cost (astra.war.stat): builds and reads since the start, and the time the builds took. */
	FString PlotStats() const;
	/** The shared lists are made again for the next reader (the bench uses it to time a build; the end of every battle tick does it already). */
	void InvalidatePlot() { ++PlotStamp; }
	/** What a battle tick costs the game thread, since the last report (astra.war.perf): the simulation, moving the hulls, the instanced drawing, the effects. */
	FString PerfReport(bool bReset);
	/** The physical state of one warship as the Aquila can know it (AstraWarDamage.cpp), for the visuals and the crew.
	 *  Detail 0: nothing known (returns false) · 1: what the eye sees (gutted, burning, venting, breaking up, disabled) ·
	 *  2: + structure by section, armour plates, shield sectors (a firm, classified track) · 3: everything, systems and
	 *  mounts too (our own side, by datalink). Facings: bow, stern, port, starboard, dorsal, ventral. Sections: bow, mid,
	 *  stern. Systems: engines, sensors, hangar, bridge, reactor, point defence. */
	struct FDamageView
	{
		struct FMountView
		{
			EAstraMountKind Kind = EAstraMountKind::Rail;
			FVector Dir = FVector::ForwardVector;   // ship frame
			float ArcDeg = 0.f;                     // half-angle of its field of fire
			uint8 Section = 0;
			float Health = 1.f;
			bool bReady = false;
		};
		int32 Id = -1;
		FString ContactId;
		int32 Detail = 0;
		EAstraSide Side = EAstraSide::Neutral;
		FVector Pos = FVector::ZeroVector;          // system frame
		FQuat Att = FQuat::Identity;
		float ShieldFrac[6] = {}, ShieldValue[6] = {}, ShieldCap[6] = {}, ShieldFlash[6] = {};
		float StructureFrac[3] = {};
		float PlateFrac[3][6] = {};
		bool bGutted[3] = {}, bBurning[3] = {}, bBreached[3] = {};
		float Sys[6] = {1, 1, 1, 1, 1, 1};
		TArray<FMountView> Mounts;
		bool bDisabled = false, bBreakingUp = false, bReactorCritical = false;
		uint8 BreakSection = 0;
		FVector BreakAxis = FVector::ZeroVector;    // the ship's long axis: the break is a plane across it (system frame)
		FVector BreakPoint = FVector::ZeroVector;   // where the plane crosses it (the class's true cut of the section that lets go)
		float CutBowX = 0.f, CutSternX = 0.f;       // the two cut planes of the break-up pieces (m along the axis, from the ship's origin)
		FVector LastHitLocal = FVector::ZeroVector; // unit vector, ship frame, out of the ship: where the last blow struck
		float LastHitAge = 1e9f;
		int32 LastHitFacing = 0;
		/** FLOTTA-VIVA: the inside as the sensors tell it, by the same detail (the holo table draws what burns and vents where, and who is left); null: it has none (the Aquila's is her own). */
		TSharedPtr<FAstraFleetView> Fleet;
	};
	bool GetDamageView(const FString& ContactId, FDamageView& Out) const;
	bool GetDamageViewById(int32 ShipId, FDamageView& Out) const;
	/** FLOTTA-VIVA (AstraFleetHooks.cpp, docs/FLOTTA-VIVA.md): the inside of a warship that is not the Aquila (null before the first blow that gets through the plating, and for the Aquila). */
	FAstraShipInterior* FleetInterior(int32 ShipId) const;
	/** What the interiors cost and did (the bench's record): ships with one, blows, casualties, the time they took. */
	TSharedRef<FJsonObject> FleetStatsJson() const;
	/** One ship's inside in a line (the console: astra.fleet.info <contact id>). */
	FString FleetInfo(const FString& ContactId) const;
	/** The console's astra.fleet.<what> <args>: info [contact] | strike <contact> <room> [energy] [kinetic|energy|explosive] | hit <contact> <face> [damage] (a blow through the war's own path). */
	FString FleetConsole(const FString& What, const TArray<FString>& Args);
	/** Deaths since the last call (a reactor breach, a breakup with its section and axis, a ship left disabled): for the
	 *  effects and the splitting of the mesh. */
	void ConsumeDeathEvents(TArray<FAstraDeathEvent>& Out);
	/** The Aquila's engines as the helm should feel them (0 = dead, 1 = sound), her damage control's help to the systems. */
	float PlayerEngineFactor() const;
	void RepairPlayerSystems(float Amount);
	/** Where a path (P0 to P1, system frame) first meets a ship's hull: the point it strikes. The hull is a box of the mesh's own measures
	 *  (a sphere of Radius for what has none). */
	bool HullSweep(const FAstraBattleShip& T, const FVector& P0, const FVector& P1, FVector& OutEntry) const;
	/** Where a beam from From, aimed at a random point of the target's side, enters its hull. */
	FVector HullRandomEntry(const FVector& From, const FAstraBattleShip& T) const;
	/** The x (along the ship's axis, from its origin) of the cut where the section that lets go breaks away. */
	float BreakX(const FAstraBattleShip& S, int32 Section) const;
	/** The Aquila in the system frame. */
	FVector PlayerPos() const { return Ships.Num() ? Ships[0].Pos : FVector::ZeroVector; }
	FVector PlayerVel() const { return Ships.Num() ? Ships[0].Vel : FVector::ZeroVector; }
	FQuat PlayerAtt() const { return Ships.Num() ? Ships[0].Att : FQuat::Identity; }
	/** The battle clock (s since the campaign started). */
	float GetBattleTime() const { return Time; }
	/** The truth, for tests and tuning (never for the crew): every ship with its side, state, orders and damage. */
	TSharedRef<FJsonObject> DebugState() const;
	/** The war bench's counters (damage by type and facing, losses by cause, focus of fire, cost per tick). */
	TSharedRef<FJsonObject> WarStatsJson() const { return Stats.ToJson(); }
	const FAstraWarStats& GetWarStats() const { return Stats; }
	/** A ship of the battle with this contact id is dead (destroyed, not merely lost from the plot). */
	bool WasDestroyed(const FString& ContactId) const;
	/** Missiles flying at the Aquila now (system frame). */
	void GetInboundMissiles(TArray<FVector>& Out) const;
	/** Where a point of the system frame is drawn in the level (cm, the bridge at the origin). */
	FVector WorldOf(const FVector& SystemPos) const { return Ships.Num() ? ToWorld(SystemPos) : FVector::ZeroVector; }
	/** Bearing and mark (degrees, the helm's convention) from the Aquila to a point of the system frame. */
	double BearingTo(const FVector& Point) const { return Ships.Num() ? BearingDeg(Ships[0].Pos, Point) : 0.0; }
	double MarkTo(const FVector& Point) const { return Ships.Num() ? MarkDeg(Ships[0].Pos, Point) : 0.0; }
	/** The Aquila's flight groups at a glance ("ALPHA 6 UP · CAP   BRAVO 7 ON DECK   DRONES REARMING"). */
	FString FlightLine() const;
	float PlayerShieldFraction() const { return Ships.Num() ? Ships[0].Shield / Ships[0].ShieldMax : 1.f; }
	bool IsScenarioOver() const { return bScenarioOver; }

	/** The campaign: nothing moves until the Captain chooses (new campaign, or continue a saved one). */
	void StartCampaign();
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
	FAstraWarStats Stats;
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
	bool bOpeningScript = true;         // the opening's stages 2 and 3 (strike group, vanguard, relief): off when the March plays them
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
	/** A fleet-scale beat (`groups`): each battle group in its formation at its own point, with its wings and its objective. */
	void ArriveGroups(const TSharedPtr<FJsonObject>& Beat, const FString& Type, const TArray<TSharedPtr<FJsonObject>>& Force, const FVector& Centre,
	                  double Bearing, const TArray<FString>& Ids);
	static constexpr int32 MaxBeatShips = 40;        // the ships one beat may bring (SCALA: 30 capital ships and 150 craft hold 60 fps)
	static constexpr int32 MaxBeatGroupShips = 10;   // the ships of one of its battle groups
	int32 SpawnClass(const FString& Class, const FString& Contact, const FString& Name, const FVector& Pos, float HeadingDeg);
	/** A Mandate ship puts decoy emitters out: drones that fly to false bearings faking a warship's drive. */
	int32 LaunchGhosts(int32 OwnerIdx, int32 N);
	UPROPERTY() TObjectPtr<UStaticMesh> SphereMesh;
	UPROPERTY() TObjectPtr<UStaticMesh> CylinderMesh;
	UPROPERTY() TObjectPtr<UMaterialInterface> GlowMat;
	UPROPERTY() TObjectPtr<UMaterialInterface> FlareMat;   // soft glow ball (drive flares)
	UPROPERTY() TObjectPtr<UMaterialInterface> ShellMat;

	/** The bridge's position in the Aquila's hull frame (m): the world origin is the bridge, not the ship centre. */
	FVector BridgeOffset = FVector(172.0, 0.0, 62.0);

	float Time = 0.f;
	// the shared plot (AstraBattleQueries.cpp): the lists are rebuilt when the stamp moves (the end of each tick, a ship added, a system cleared)
	uint32 PlotStamp = 1;
	mutable TArray<FContactView> ContactsCache;
	mutable TArray<FAstraHoloBlip> BlipsCache;
	mutable FPlotCounts CountsCache;
	mutable uint32 ContactsBuiltAt = 0, BlipsBuiltAt = 0;
	mutable int32 ContactBuilds = 0, ContactReads = 0, BlipBuilds = 0, BlipReads = 0;
	mutable double ContactMs = 0.0, BlipMs = 0.0;
	struct FPerfWindow
	{
		double Sim = 0.0, Sync = 0.0, Draw = 0.0, Fx = 0.0, Total = 0.0, TotalMax = 0.0;
		int32 Frames = 0;
	};
	FPerfWindow PerfWin;
	void BuildContacts(TArray<FContactView>& Out) const;
	void BuildHoloBlips(TArray<FAstraHoloBlip>& Out, FPlotCounts& Counts) const;
	bool bPlayerTracked = true;
	bool bPlayerEverTracked = false;   // since hostiles appeared: "lost" needs a track first
	float PlayerTrackT = 0.f;
	float PlayerSinceFired = 999.f;
	FVector PlayerLastKnown = FVector::ZeroVector;
	void TickDetection(float Dt);
	/** The Aquila's own picture of the Mandate's ships: passive bearings from their emissions, tracks from the active
	 *  sensors (EMCON) and the friends' datalink, classification and identity as they close; reported as they change. */
	void TickSensors(float Dt);
	/** The Captain's Falcon against the hulls (the Aquila's collision, the others' boxes): true if she was lost. */
	bool PilotCollision(FAstraBattleShip& S, const FVector& Prev);
	float SignatureKmOf(const FAstraBattleShip& S) const;
	/** How the crew can name it: "KMS Lethe (T-31)", "a Mandate frigate (T-31)" or "T-31". */
	FString KnownLabel(const FAstraBattleShip& S) const;
	float SensorReportT = 0.f;
	float Shake = 0.f;
	int32 InboundSinceReport = 0;       // missiles launched at us since the last spoken report
	float LastInboundReport = -100.f;
	int32 NextId = 1;
	int32 StageDone = 0;                // the opening's script: 1 the frigate wakes, 2 the strike group, 3 the gate cycles (the vanguard and the relief on their way)
	static constexpr int32 OpeningOver = 9;
	float StageTwoAt = -1.f;            // when the strike group came (the vanguard follows it)
	float VanguardAfterS = 330.f;       // how long after the strike group the Interdiction Fleet's vanguard comes through the gate
	TArray<TPair<float, FString>> TransmissionNotes;   // reports that come at their time (Fleet's word on a relief under way)
	/** The opening grows into a fleet battle: the Interdiction Fleet's vanguard through the gate, the 7th Fleet's relief from New Ravenna. */
	void ScheduleOpeningForce(const TCHAR* Which, float At);
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
	bool bPilotAuto = false;              // the recovery guidance flies the Falcon (StartPilotRecovery)
	int32 PilotAutoLeg = 0;               // 0 clear of the hull, 1 to the approach gate, 2 down the axis to the mouth
	float PilotTakeBackT = 0.f;           // how long the stick has been pushed hard against the guidance
	void TickPiloted(FAstraBattleShip& S, float Dt);
	void TickPilotRecovery(FAstraBattleShip& S, float Dt);
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
	// --- the craft's minds (AstraWarCraft.cpp)
	void AssignFlight(FAstraBattleShip& C, int32 Squadron);
	FAstraFlight* FindFlight(int32 Id);
	FVector CraftAvoidance(const FAstraBattleShip& S) const;
	FVector EnvelopeWall(const FAstraBattleShip& S, const FVector& Steer) const;
	void ThinkCraft(FAstraBattleShip& S, float DtT);
	void FireCraft(FAstraBattleShip& S, float Dt);
	void LandCraft(FAstraBattleShip& S, FAstraBattleShip& Carrier, FAstraSquadron& Q);
	int32 AirborneCount(int32 Squadron) const;
	// --- the Captain's wing (AstraWarCraft.cpp, docs/VOLO.md): when he leaves the catapult in a Falcon, two more of Alpha's Falcons follow from the tubes and fly his
	// wing as Eagle 2 and Eagle 3 (an escort flight that he leads); what happens to them is told as `flight: Eagle 2 ...` for the flight net's people to speak
	int32 WingToLaunch = 0;              // Falcons still to come off the deck
	int32 WingLaunched = 0;
	float WingLaunchT = 0.f;
	int32 WingFlightId = -1;
	void StartEagleWing();
	void TickEagleWing(float Dt);
	void EndEagleWing();
	void WingNotes(FAstraBattleShip& S);
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
	/** A blow lands: FromDir is the direction of travel, HitPos where it strikes the hull; Kind says what it is (and so how
	 *  shields and armour take it); SourceId is the ship that fired (-1: none). */
	void ApplyHit(FAstraBattleShip& To, const FVector& FromDir, float Damage, const FVector& HitPos, EAstraHitKind Kind, int32 SourceId);
	void Destroy(FAstraBattleShip& S, EAstraHitKind Cause = EAstraHitKind::Internal, EAstraFate How = EAstraFate::Destroyed, uint8 Section = 0);

	// --- the hierarchy and the minds (AstraWarKnowledge.cpp, AstraWarShipAI.cpp, AstraWarGroups.cpp, AstraWarCraft.cpp)
	TArray<FAstraBattleGroup> Groups;
	TArray<FAstraFlight> Flights;
	int32 NextGroupId = 1, NextFlightId = 1;
	FAstraWarGrid Grid;
	TArray<int32> CapIdx;               // this tick: the alive warships (indices in Ships)
	TArray<int32> CraftBySide[2];       // this tick: the alive craft of each side (a search over a long reach goes down this list, not the grid)
	bool bStandDownCache = false;       // this tick: the Mandate leader has agreed to terms (bMandateStandDown, asked by every craft)
	TArray<int32> HulkIdx;              // and the hulks that are obstacles (indices in Wrecks)
	TMap<int32, int32> IdIndex;         // ship id -> index in Ships
	float KnowledgeT = 0.f, GroupAssignT = 0.f, CompactT = 0.f;
	void RebuildIdIndex();
	void CompactShips();
	void BuildGrid();
	float SignatureOf(const FAstraBattleShip& T) const;
	double SensorReachM(const FAstraBattleShip& O) const;
	void TickKnowledge();
	/** Does this side hold that ship on its sensors now (or a moment ago); where it believes it is. */
	bool Knows(int32 SideIdx, const FAstraBattleShip& T) const;
	FVector KnownPos(int32 SideIdx, const FAstraBattleShip& T) const;
	double ShipDps(const FAstraBattleShip& S, double RangeM) const;
	float Readiness(const FAstraBattleShip& S) const;
	bool CanEngage(const FAstraBattleShip& S, const FAstraBattleShip& O) const;
	FAstraBattleGroup* FindGroup(int32 Id);
	const FAstraBattleGroup* FindGroup(int32 Id) const { return const_cast<UAstraBattleSubsystem*>(this)->FindGroup(Id); }
	// the commanders' tools (AstraWarOrders.cpp)
	TArray<FAstraGroupEvent> GroupEvents;
	int32 NextGroupEventSerial = 1;
	void NoteGroupEvent(int32 SideIdx, const FString& Text);
	void SetGroupState(FAstraBattleGroup& G, EAstraGroupState New, const FString& Why);
	void NoteGroupLoss(const FAstraBattleShip& S, const TCHAR* How);
	FAstraBattleGroup* ResolveGroup(const FString& Key, int32 SideIdx, FString* OutWhy = nullptr);
	FString DescribeGroupOrder(const FAstraBattleGroup& G, const FAstraBattleShip* Target, const FAstraBattleGroup* Other) const;
	/** Is this enemy ship on the side's plot now (its ships' sensors; for ASTRA also the Aquila's own plot), and where. */
	bool OnPlot(int32 SideIdx, const FAstraBattleShip& X, FVector& OutPos) const;
	FAstraBattleShip* ChooseTarget(FAstraBattleShip& S, FAstraBattleGroup* G);
	FVector ChooseFacing(const FAstraBattleShip& S, const FVector& ToTarget, double Dist) const;
	FVector AvoidanceVel(const FAstraBattleShip& S) const;
	void TickShipAI(FAstraBattleShip& S, float Dt);
	void ThinkShip(FAstraBattleShip& S, float DtT);
	void ThinkWithdraw(FAstraBattleShip& S, FAstraBattleGroup* G);
	void TickPointDefence(FAstraBattleShip& S);
	int32 NewGroup(EAstraSide Side, const FString& Name, EAstraFormation Formation);
	void JoinGroup(FAstraBattleShip& S, int32 GroupId);
	int32 NoteGroupSpawn(EAstraSide Side, const FString& Name, const FString& Formation, const TArray<int32>& ShipIdx, int32 ProtecteeId);
	void AssignGroups();
	void TickGroups(float Dt);
	void ThinkGroup(FAstraBattleGroup& G, float DtT);
public:
	/** The minds' orders on a battle group (docs/GUERRA.md, the menu): auto | attack | attack_group | pin | flank_left |
	 *  flank_right | screen | withdraw | regroup | reinforce | hold. */
	bool SetGroupOrder(int32 GroupId, const FString& Order, const FString& ShipContact, int32 OtherGroup, float Duration, const FString& By, FString& OutDetail);
	/** The battle groups as the bench reads them (state, order, formation, focus, range, strengths). */
	TSharedRef<FJsonObject> GroupsJson() const;
	/** The `group_order` command of the minds: {side, group, order, target, for_s, by, formation}. The detail says, in plain
	 *  English, what the group will do. Only the callers a side allows may order its groups (docs/GUERRA.md). */
	bool GroupOrderCommand(const TSharedPtr<FJsonObject>& Args, FString& OutDetail);
	/** One side's groups as its mind may read them, the fog of war applied: { your_groups, enemy_groups, group_events }.
	 *  Side 0 is the snapshot's `_astra_groups`, side 1 is merged into `_mandate`. */
	TSharedRef<FJsonObject> SideGroupsJson(int32 SideIdx) const;
private:

	// --- bench scenarios (AstraWarScenario.cpp)
	bool bSandbox = false;              // no Aquila, no script: a scenario of the bench is running
	void ProcessWarCommands();
	void SandboxReset(bool bKeepAquila = false);
	int32 SpawnByKey(FName Key, EAstraSide Side, const FString& Contact, const FString& Name, const FVector& Pos, float HeadingDeg);
	/** A flight group aboard a carrier (kind 0 fighter, 1 bomber, 2 drone), launching after Delay seconds; its index. */
	int32 AddWing(int32 CarrierIdx, int32 Kind, int32 Count, const FString& Mission, float Delay);
	bool LoadScenario(const FString& Name, FString& OutDetail, bool bWithAquila = false, const TArray<FString>& Options = TArray<FString>());
	/** One group of a scenario file made (its ships in formation, its wings, a battle group for them): at the start, or as a wave. Its group id (INDEX_NONE: no ships). */
	int32 SpawnScenarioGroup(const TSharedPtr<FJsonObject>& G, EAstraSide Side, int32 SideIdx, bool bRotated, int32& Spawned, int32& Wings, FString& OutName, FString& OutProtects);
	/** The "wings" of a group (or of the Aquila): each is a flight group aboard the ship of Made that its "carrier" index names. How many were made. */
	int32 AddScenarioWings(const TArray<TSharedPtr<FJsonValue>>& List, const TArray<int32>& Made);
	/** A wave of a scenario file (reinforcements: "waves", in a file of data/war/scenarios): a group that arrives when its time comes. */
	struct FScenarioWave
	{
		float At = 0.f;
		TSharedPtr<FJsonObject> Group;
		EAstraSide Side = EAstraSide::Astra;
		bool bDone = false;
	};
	TArray<FScenarioWave> ScenarioWaves;
	int32 ScenarioCounter[2] = {1, 1};         // the next contact number of each side's scenario ships
	void TickScenarioWaves();

	// --- the physical model (AstraWarDamage.cpp)
	// --- the inside of the other ships (AstraFleetHooks.cpp, docs/FLOTTA-VIVA.md): the Aquila's damage model on the plan of their class
	bool FleetOn() const;
	FAstraShipInterior* FleetEnsure(FAstraBattleShip& S);
	void FleetOnHit(FAstraBattleShip& To, const FAstraHullHit& Hit);
	void FleetOnGutted(FAstraBattleShip& S, int32 Section);
	void FleetTick(FAstraBattleShip& S, float Dt);
	/** What a side's mind (or an observer's sensors) may read of a ship's inside, added to its entry in a view: bOwn the ship's own side (everything), else by Detail (1 the eye, 2 a classified track). */
	void FleetBriefInto(const FAstraBattleShip& S, const TSharedRef<FJsonObject>& Into, bool bOwn, int32 Detail) const;
	float FleetFactor(const FAstraBattleShip& S, int32 Category) const;
	mutable double FleetMs = 0.0, FleetMsMax = 0.0;
	mutable int32 FleetBlows = 0, FleetTicks = 0;
	void InitShipModel(FAstraBattleShip& S);
	/** (Re)build a ship's sections, plates and shield sectors for a hull and a shield total (full health). */
	void BuildDurability(FAstraBattleShip& S, float Hull, float Shield);
	void SyncTotals(FAstraBattleShip& S) const;
	void SetShieldFocus(FAstraBattleShip& S, int32 Facing, float K);
	float EngineFactor(const FAstraBattleShip& S) const;
	float PowerFactorOf(const FAstraBattleShip& S) const;
	float SensorFactor(const FAstraBattleShip& S) const;
	float HangarFactor(const FAstraBattleShip& S) const;
	void AddHullDelta(FAstraBattleShip& S, float Delta);
	void SetHullFraction(FAstraBattleShip& S, float Frac);
	void ApplyHitLump(FAstraBattleShip& To, const FVector& FromDir, float Damage, const FVector& HitPos, EAstraHitKind Kind, int32 SourceId);
	void ApplyHitModel(FAstraBattleShip& To, const FVector& FromDir, float Damage, const FVector& HitPos, EAstraHitKind Kind, int32 SourceId);
	float StructureDamage(FAstraBattleShip& S, int32 Sec, float Amount, EAstraDamageType Type, const FVector& N, int32 F);
	void DamageInside(FAstraBattleShip& S, int32 Sec, float Taken, float SystemMul, const FVector& N, int32 F);
	void OnSectionGutted(FAstraBattleShip& S, int32 Sec);
	void DisableShip(FAstraBattleShip& S, const TCHAR* Why);
	void KillModelShip(FAstraBattleShip& S, EAstraFate How, EAstraHitKind Cause, int32 Section);
	void TickShields(FAstraBattleShip& S, float Dt);
	void TickDamageState(FAstraBattleShip& S, float Dt);
	int32 BearingBarrels(const FAstraBattleShip& S, EAstraMountKind Kind, const FVector& AimDir) const;
	void FireMounts(FAstraBattleShip& S, FAstraBattleShip& T, double Dist);
	TArray<FAstraDeathEvent> DeathEvents;
	void BreakCeasefire(const FAstraBattleShip& Victim);
	/** The Mandate commander's ship is gone (destroyed or jumped out): the next captain in line takes over and calls. */
	void OnCommanderLost(const FAstraBattleShip& Old, const TCHAR* How);
	void AddFlash(const FVector& Pos, float Size, float Life, const FLinearColor& Color, float Intensity, EAstraFxFlash Kind);
	void AddFlash(const FVector& Pos, float Size, float Life, const FLinearColor& Color, float Intensity);
	/** A beam or a tracer line (what it is, and the ships at its ends so that it rides on them while it lives). */
	void AddBeam(const FVector& A, const FVector& B, float Life, const FLinearColor& Color, EAstraFxShot Kind, int32 FromId = -1, int32 ToId = -1);
	void AddBeam(const FVector& A, const FVector& B, float Life, const FLinearColor& Color);
	/** The war's visual effects (AstraWarFX.cpp): the shots, the flashes, the shields, the explosions and the broken hulls are drawn by it
	 *  once its materials are in the project (tools/ue_scripts/make_war_fx.py); until then the older drawing below stands. */
	UPROPERTY() TObjectPtr<UAstraWarFX> WarFX;
	bool FxOn() const;
	/** The craft and the lamps as instances (AstraWarDraw.cpp): a craft it claims at SpawnVisual has no actor, and no ship it draws the lamps of has a running-light component. */
	UPROPERTY() TObjectPtr<UAstraWarDraw> WarDraw;
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
