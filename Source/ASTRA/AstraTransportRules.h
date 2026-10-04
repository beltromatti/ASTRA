// ASTRA — TELETRASPORTO, the rules of the lattice transport (docs/TELETRASPORTO.md, docs/BIBBIA.md §4): who and what can be carried, from where to where,
// and what stands in the way. Plain code over a snapshot of the world (no actors, no subsystems): it says whether a beam can be made now and why not, how
// long the lock takes, how good it is and what it costs. The world around it (the battle's shields and jamming, the ship's motion, the damage model's room
// and power, the planet) is read by UAstraTransporterSubsystem into an FEnv; the bench (AstraTransportCommandlet) feeds it made-up worlds and checks every
// rule on scripted cases. Deterministic from a seed; every number is in data/ship/aquila_transport.json.
//
// The physics, in a few lines (the canon is BIBBIA §4):
//  - the beam leaves our hull through the face that looks at the other end and enters theirs through the face that looks at us (GUERRA's six shield
//    sectors: bow, stern, port, starboard, dorsal, ventral); a face is open when its shield is down or its sector is spent, and ONE open face at each end is enough;
//  - range (30,000 km, less when the room or the sensors are weak), electronic jamming along the line, a ship that accelerates or turns hard, the field of a
//    Janus Gate: they spoil the lock, and past a limit they forbid it;
//  - a lock takes time to build, has a quality that follows the conditions, and is lost when the quality stays low;
//  - a cycle is eight seconds and 40 MW; a pattern waits in the buffer at most 90 s;
//  - the room's own state (the damage model's power, wreck, fire, air) and the destination's hazards decide whether the beam may be made at all.

#pragma once

#include "CoreMinimal.h"

namespace AstraXport
{
	constexpr int32 NumFaces = 6;      // bow, stern, port, starboard, dorsal, ventral: the order of AstraWar::EFacing

	// ------------------------------------------------------------------------------------------------ the numbers
	/** Everything the rules read: data/ship/aquila_transport.json over these defaults. */
	struct ASTRA_API FTuning
	{
		// limits
		float MaxRangeKm = 30000.f, EmergencyRangeKm = 400.f;
		int32 Pads = 6, EmergencyPads = 2;
		float MassKgPerPad = 2000.f, CargoKg = 2000.f;
		float CycleS = 8.f, WarmupS = 0.4f, DematS = 3.6f, RematS = 3.6f, SettleS = 0.4f;
		float CycleMW = 40.f, ExtraSubjectMW = 6.f, BufferHoldS = 90.f, HeatPerCycle = 0.6f;
		// the lock
		float LockAboardS = 1.5f, LockShipS = 3.5f, LockHostileExtraS = 2.f, LockSurfaceS = 5.f, LockPer1000KmS = 0.6f, LockMaxS = 30.f;
		float AcquireQ = 0.55f, HoldQ = 0.40f, LoseQ = 0.25f, LoseGraceS = 0.8f, RiseS = 1.5f, FallS = 0.4f;
		// shields, motion, the gate
		float ShieldOpenBelow = 0.05f;
		float AccelWarn = 3.f, AccelBlock = 9.f, TurnWarn = 0.8f, TurnBlock = 2.f, TargetTurnWarn = 3.f, GateFieldKm = 25.f, GateApproachQ = 0.5f;
		// jamming
		float JamBlock = 0.6f, JamWarn = 0.25f, JamSigmaDeg = 9.f, JamRangeRefKm = 60.f, JamOwnFloor = 0.15f;
		float GroundJam[5] = {0.f, 0.05f, 0.3f, 0.55f, 0.15f};   // by who holds the world below: astra, guilds, contested, mandate, silent
		// the world below
		float OrbitKm = 1200.f;
		FVector2D LandingOffsetM = FVector2D(4.5, 3.0);
		// hazards at the arrival, the room's own state
		float AirMin = 0.6f, FireMax = 0.2f, SmokeMax = 0.5f, HeatMax = 0.45f;
		float RoomOffline = 0.12f, RoomDegraded = 0.6f;
		float ShieldLoad = 0.2f, ShieldFloor = 0.25f;
		float AllyEngagedKm = 12.f;
		TArray<FName> InhibitKinds;
		TArray<FName> InhibitIds;
		// the failures of a rematerialization
		float DelayP = 0.9f, DelayMinS = 2.f, DelayMaxS = 10.f, OffsetP = 0.3f, OffsetM = 6.f, ScatterBelow = 0.3f;
		// the room's frame (the plan gives the room's place; this is where things stand inside it)
		FName RoomKind = TEXT("transporter");
		FVector2D DaisCentre = FVector2D(17.0, 8.6);
		float RingM = 2.f, FirstDeg = 0.f, PadZM = 0.312f, PadRM = 0.62f;
		FVector2D CargoCentre = FVector2D(4.6, 13.0);
		float CargoZM = 0.2f, CargoRM = 0.8f;
		FVector EmitterM = FVector(17.0, 8.6, 2.95);
		FVector2D ChiefStand = FVector2D(8.4, 8.6);
		float ChiefYaw = 0.f;
		FVector WallScreenM = FVector(23.725, 7.0, 1.395);
		FVector2D WallScreenSizeM = FVector2D(4.1, 1.85);
		float WallScreenYaw = 180.f;
		struct FEmergency { FName Id, Room; FVector PosM = FVector::ZeroVector; float PadRM = 0.6f; };
		TArray<FEmergency> Emergency;

		/** The data file (the staged copy first, then the repository's); true when it was read. Without it the defaults above stand. */
		bool Load(const FString& OptionalPath = FString());
		/** One line for the log. */
		FString Describe() const;
	};

	// ------------------------------------------------------------------------------------------------ the world, as the rules see it
	enum class EAllegiance : uint8 { Own, Allied, Neutral, Hostile, Derelict };
	enum class EEndKind : uint8 { Pad, Site, Ship, Surface };
	enum class ESubject : uint8 { Captain, Person, Cargo };

	/** A hull at one end of the beam (or anywhere near it): where it is, which way it points, how big, and what its shield sectors hold. */
	struct ASTRA_API FHull
	{
		bool bPresent = false;
		FString Id, Name;
		EAllegiance Side = EAllegiance::Neutral;
		bool bShieldsUp = true;
		bool bDisabled = false;               // no power: no shield
		bool bFacesKnown = true;              // the sensors tell the shield state (a firm, classified track); false: the crew can only guess
		float Frac[NumFaces] = {1, 1, 1, 1, 1, 1};   // each sector's charge over its capacity
		FVector Pos = FVector::ZeroVector;    // the hull's origin, system frame (m)
		FQuat Att = FQuat::Identity;
		FVector Centre = FVector::ZeroVector; // the box's centre, system frame (m)
		FVector Half = FVector(150, 30, 30);  // the box's half extents along its own axes (m)
		FVector Vel = FVector::ZeroVector;    // m/s
		float TurnDegS = 0.f;                 // how hard it is turning
		float AccelMps2 = 0.f;
		bool bEngaged = false;                // in a fight: firing, or a hostile ship close by (an ally will not open an aperture)
		bool bJamming = false;                // a Mandate capital ship jamming along its bearing
		float RadiusM = 100.f;
	};

	/** The state of a compartment as the damage model holds it. */
	struct ASTRA_API FRoomState
	{
		bool bExists = true;
		FString Name;
		float Power = 1.f;                    // 0..1
		float Wreck = 0.f;                    // 0..1 (1: gutted)
		float Air = 1.f, Fire = 0.f, Smoke = 0.f, Heat = 0.f;
		bool bLocked = false, bGutted = false;
	};

	struct ASTRA_API FSubject
	{
		ESubject Kind = ESubject::Person;
		FString Id;                           // "captain", "npc17", "cargo"
		FString Label;                        // "the Captain", "Lieutenant Sato", "300 kg of medical supplies"
		float MassKg = 90.f;
		int32 Roster = INDEX_NONE;
		bool bFound = true;                   // the pattern can be located
		bool bAway = false;                   // already off the ship
		bool bDead = false;
		bool bInPattern = false;              // already in a transport (a second order for the same person)
		FString Barred;                       // a plain reason this one cannot be carried at all (a post that cannot be left): empty = free to go
	};

	/** One end of a transport. */
	struct ASTRA_API FEnd
	{
		EEndKind Kind = EEndKind::Site;
		FString Label;
		bool Aboard() const { return Kind == EEndKind::Pad || Kind == EEndKind::Site; }
		// aboard (a pad or a site)
		bool bPad = false, bEmergencyPad = false;
		int32 Pad = INDEX_NONE;
		bool bPadOccupied = false;
		FName CompKind, CompId;
		bool bInhibited = false;
		FString OpenNear;                  // a shielded room: the nearest one on its deck that the beam reaches (what the refusal offers instead)
		FRoomState Room;                      // the compartment
		bool bHazard = false;                 // (filled by Evaluate from Room)
		// a ship
		FHull Ship;
		// the world below
		FString World;
		uint8 Owner = 0;                      // 0 astra, 1 guilds, 2 contested, 3 mandate, 4 silent
		FVector DirBody = FVector(0, 0, -1);  // from the Aquila to the planet in her own frame (unit)
		bool bBeacon = true;                  // a field's beacon helps the lock
	};

	/** The Aquila and everything the beam depends on. */
	struct ASTRA_API FEnv
	{
		FHull Own;
		float AccelMps2 = 0.f, TurnDegS = 0.f;
		bool bGateLane = false, bGateApproach = false;
		float GateKm = -1.f;
		float SensorsPower = 1.f, ShieldsPower = 1.f, HeatFactor = 1.f;
		bool bReactorOn = true;
		FRoomState Main, Emergency;           // the transporter room, and the Medbay's pads' room
		TArray<FHull> Others;                 // every other hull: jamming comes from them
	};

	struct ASTRA_API FRequest
	{
		TArray<FSubject> Subjects;
		FEnd From, To;
		bool bShieldWindow = false;           // Tactical will hold our shields down for the cycle (the order carries it)
		bool bOverrideHazard = false;         // the Captain's word: land them in the hazard anyway
		bool bForce = false;                  // the Captain's word: beam through the soft limits (a degraded lock)
	};

	// ------------------------------------------------------------------------------------------------ the verdict
	struct ASTRA_API FBlocker
	{
		FName Code;                           // shields_own, shields_theirs, range, jam, motion, gate, room, hazard, inhibit, occupied, mass, pads, subject, power, target, quality
		FString Why;                          // one plain English sentence, with the numbers
		FString Fix;                          // what would clear it
		bool bHard = true;                    // nothing the Captain's word can change (the laws of the beam)
		bool bOverridable = false;            // the Captain may order it anyway (and takes the consequences)
	};

	struct ASTRA_API FVerdict
	{
		bool bOk = false;
		TArray<FBlocker> Blockers;
		TArray<FString> Notes;                // what degrades the lock but does not forbid it
		TArray<FString> Unknown;              // what the sensors cannot tell (a face's shield state)
		bool bEmergencySystem = false;        // the Medbay's pads do it
		float RangeKm = 0.f;
		float MaxRangeKm = 0.f;
		float LockS = 0.f;                    // time to a lock at the quality below
		float Quality = 1.f;                  // 0..1 target of the lock's quality now
		float CycleS = 8.f;
		float EnergyMW = 40.f;
		int32 OwnFace = INDEX_NONE, TheirFace = INDEX_NONE;   // the faces the beam crosses (NumFaces: none)
		bool bNeedsOwnWindow = false;         // our shields must be down for the cycle
		bool bOwnOpen = true, bTheirsOpen = true;
		float Jam = 0.f;
		bool HasBlocker(const TCHAR* Code) const;
		FString Summary() const;              // the blockers in one line, for the log and the console
	};

	// ------------------------------------------------------------------------------------------------ the rules
	/** The face of a box (ship frame: x forward, y starboard, z up) that the line from its centre to a point leaves through: the sector a beam
	 *  to that point crosses. Half: the box's half extents. */
	ASTRA_API int32 FaceToward(const FQuat& Att, const FVector& Centre, const FVector& Half, const FVector& Point);
	/** The same for a direction given in the hull's own frame. */
	ASTRA_API int32 FaceOfLocalDir(const FVector& LocalDir, const FVector& Half);
	/** Is that face of the hull open to a beam: shields down, the ship disabled, or the sector spent. */
	ASTRA_API bool FaceOpen(const FHull& H, int32 Face, const FTuning& T);
	/** Jamming along the beam from the Aquila to `To` (system frame, m): 0..1, from every jamming hull but the Aquila's friends. */
	ASTRA_API float JamAlong(const FEnv& Env, const FVector& To, const FString& IgnoreId, const FTuning& T);
	/** Can this request be carried out now, and how (see the header). The same call serves the crew's pre-flight (a fog-of-war env) and the real thing (the truth). */
	ASTRA_API FVerdict Evaluate(const FTuning& T, const FEnv& Env, const FRequest& Req);
	/** The lock's quality the conditions allow right now (0..1) for a request already known to be possible, with the notes of what costs it. */
	ASTRA_API float LockTarget(const FTuning& T, const FEnv& Env, const FRequest& Req, const FVerdict& V, TArray<FString>* OutNotes = nullptr);
	/** The lock's state machine: quality eases to its target (slow up, fast down); `Progress` is the share of the lock built; lost when quality stays under LoseQ. */
	struct ASTRA_API FLock
	{
		enum class EState : uint8 { Acquiring, Locked, Degraded, Lost };
		EState State = EState::Acquiring;
		float Quality = 0.f;                  // 0..1, now
		float Progress = 0.f;                 // 0..1: the share of the lock built
		float LowT = 0.f;                     // seconds the quality has been under LoseQ
		float NeedS = 3.f;                    // seconds a lock takes at full rate
		void Begin(float InNeedS) { State = EState::Acquiring; Quality = 0.f; Progress = 0.f; LowT = 0.f; NeedS = FMath::Max(0.2f, InNeedS); }
		/** Advances Dt seconds under the conditions: Target is LockTarget(); Rate scales the build speed. */
		void Tick(const FTuning& T, float Dt, float Target, float Rate);
		bool IsLocked() const { return State == EState::Locked || State == EState::Degraded; }
		static const TCHAR* Name(EState S);
	};
	/** What happens to a pattern when it comes back: nothing, held in the buffer a while, set down off the mark, or scattered (lost). Drawn from the seed, never from a clock. */
	enum class EArrival : uint8 { Clean, Delayed, Offset, Scattered };
	struct ASTRA_API FArrival
	{
		EArrival Kind = EArrival::Clean;
		float DelayS = 0.f;                   // Delayed: seconds in the buffer on top
		float OffsetM = 0.f;                  // Offset: how far off the mark
	};
	ASTRA_API FArrival RollArrival(const FTuning& T, float MinQuality, bool bForced, FRandomStream& Rng);
	/** How long the lock needs for this request (seconds at full rate): the kind of end, the range, the jam. */
	ASTRA_API float LockSeconds(const FTuning& T, const FEnv& Env, const FRequest& Req, float RangeKm, float Jam);
	/** The range the room can reach now (km): the data's maximum scaled by the room's power and the sensors'. */
	ASTRA_API float ReachKm(const FTuning& T, const FEnv& Env, bool bEmergency);
	/** The cycle's time (seconds), stretched when the room is weak. */
	ASTRA_API float CycleSeconds(const FTuning& T, const FRoomState& Room);
	/** Energy (MW) for a party of N. */
	ASTRA_API float EnergyFor(const FTuning& T, int32 N);
	/** The id of an allegiance for the log. */
	ASTRA_API const TCHAR* AllegianceName(EAllegiance A);
	/** The face names, like AstraWar::FacingName. */
	ASTRA_API const TCHAR* FaceName(int32 Face);
}
