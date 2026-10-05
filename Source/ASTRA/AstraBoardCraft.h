// ASTRA — ABBORDAGGI-2: the assault craft of the war (docs/brief/ABBORDAGGI-2.md §1).
//
// A boarding is not a wall that opens in a hull: somebody flies to it. The Kharon Mandate's boarding skiff (ten men) and the Aquila's Kestrel (twelve marines, from the assault-shuttle bay on
// Deck 8) are craft of the battle like the Falcons and the Harpies: they have a hull, they are seen, point defence and fighters shoot at them, and what they do is a flight (leave the
// carrier, cross to the target, slow down, line up with a hatch on her skin, latch, cut in). The docking is what opens the breach: the host of the boarding (UAstraBoardSubsystem) reads
// the battle's events (launched, docked, destroyed, departed) as it reads the deaths.
//
// This file is the plain data (the kinds of craft, what a ship carries, the flight's state, the events and the facts a mind is told); the flight and the rules are the battle's
// (AstraBoardCraft.cpp, members of UAstraBattleSubsystem), the people in the craft are the host's.
//
// The rules of the world, and only those, are code: a craft passes the point defence of the target if it survives it (its chance per shot is its own: armoured, but a hull of 140), it docks
// where the shield on that face is down (or the ship has no power), it cuts in a while after it touches. Whether to board, where and with how many is the minds' (they are told the truth
// by AssessBoarding: the shield, the point defence, the fighters in the way).

#pragma once

#include "CoreMinimal.h"

namespace AstraBoardCraft
{
	constexpr double StageM = 420.0;          // how far in front of its hatch a craft ends its crossing and begins the approach (m)
	constexpr float ShieldDownFrac = 0.08f;   // a shield sector below this share of its capacity lets a craft through
	constexpr double BrakeShare = 0.55;       // a boat brakes at this share of its thrust (the flight's own rule: AstraBoardFlight.cpp)
	constexpr double LeaveS = 3.0;            // from the catapult to clear of the hull, on the bay's axis
	constexpr double ApproachMaxMps = 55.0;   // the closing speed down a hatch's axis: 0.30 per second of the distance left, at most this, at least 2.5 m/s (AstraBoardFlight.cpp)

	/** What a boat is. */
	struct FKind
	{
		FName Key;                       // skiff | kestrel
		const TCHAR* Callsign;           // "Skiff", "Kestrel"
		const TCHAR* Mesh;               // SM_CRAFT_MANDATE_Skiff, SM_CRAFT_ASTRA_Kestrel
		const TCHAR* ClassText;          // what its contact says it is
		bool bMandate;
		int32 Men;                       // how many it carries
		float Hull;
		float Radius;                    // m: the sphere a gun strikes
		float HalfLength;                // m: how far its nose is from its centre (it touches the hull with it)
		float Cruise;                    // m/s, against the ship it flies to or from (its flight is flown in her frame: a hull that runs at 450 m/s is no faster to catch)
		float Accel;                     // m/s^2
		float PdHit;                     // the chance that a point-defence shot finds it (a fighter's is 0.07 to 0.14): an armoured boat, slower, but a hull of 140 to 200
		float PdDamage;                  // and what a hit does
		float LatchS;                    // from touching the hull to the cut: seconds
	};

	/** The two kinds. */
	ASTRA_API const FKind& Skiff();
	ASTRA_API const FKind& Kestrel();
	ASTRA_API const FKind* KindByKey(FName Key);

	/** How far from her keel line the Aquila's plating stands at a station of her hull (m along her mesh's x): the boats latch to it, and the bay's mouth is on it. Measured on the generated mesh
	 *  (the plan's outer wall stands about four metres inside it: it is the airlocks' wall, not the skin). */
	ASTRA_API double AquilaSkinM(double HullXm);

	/** What a class carries: how many boats of which kind (skiffs for the Mandate's ships, Kestrels for ASTRA's), and where they leave and come home. Count 0: none. */
	struct FBerths
	{
		const FKind* Kind = nullptr;
		int32 Count = 0;
		FVector Bay = FVector::ZeroVector;           // m, the hull's frame: the mouth of the boat bay
		FVector BayNormal = FVector(0.0, -1.0, 0.0); // out of the hull there
	};
	ASTRA_API FBerths BerthsOf(FName ClassKey, const FVector& HullHalfM, float HullMidM);

	enum class EPhase : uint8
	{
		Idle,         // not yet out of the bay
		Leaving,      // out of the bay, clear of the hull
		Transit,      // across to a point in front of its hatch (or in front of the bay mouth, going home)
		Approach,     // down the hatch's axis to the hull
		Hold,         // the shield on that face is up: it waits off the hull (the point defence still shoots)
		Latching,     // touching: clamped and cutting in
		Docked,       // the way in is open: the men are aboard (the host's)
		Undocking     // the fight is over: off the hull
	};
	ASTRA_API const TCHAR* PhaseName(EPhase P, bool bHome);

	// ---- the flight's clock: what the minds and the ride's screen are told is what the flight does (the same rules, not a guess). Every number is seconds or metres.
	/** How long a boat takes to cross DistM in a straight line, from rest against its goal to rest there: it climbs to its cruise, holds it, and brakes at BrakeShare of its thrust. */
	ASTRA_API double CrossS(const FKind& K, double DistM);
	/** How long the last leg takes, down the hatch's axis from AlongM to touching: closing speed 0.30 per second of the distance left, at most ApproachMaxMps, at least 2.5 m/s. */
	ASTRA_API double ApproachS(double AlongM);
	/** From the boat leaving the bay to the way in being cut open, for a hatch DistM from the carrier's bay (the target's hull, StageM and the touch not counted twice). */
	ASTRA_API double FlightEtaS(const FKind& K, double DistToHatchM);
	/** What is left of a flight for a boat in a phase: DistToStageM is the way to the point StageM in front of the hatch (or of the bay's mouth), AlongM the way down the axis, PhaseT the seconds in the phase. */
	ASTRA_API double RemainingS(const FKind& K, EPhase Phase, bool bHome, double DistToStageM, double AlongM, float PhaseT);
	/** A time as one says it: "45 s", "1 min 40 s", "about 3 minutes" is the caller's. */
	ASTRA_API FString SpanText(double Seconds);

	/** The flight of a boarding craft: the state a ship of the battle keeps while it flies one (CraftKind 3). */
	struct FFlight
	{
		EPhase Phase = EPhase::Idle;
		bool bHome = false;              // going back to the carrier's bay (after the fight, or turned back)
		int32 Order = -1;                // the assault it flies in (the host's number)
		int32 Leg = 0;                   // its number in the assault
		int32 TargetId = -1;
		int32 CarrierId = -1;
		int32 Men = 0;                   // aboard
		bool bUnloaded = false;          // the men have gone through
		bool bCaptain = false;           // the Captain rides in it
		FName Kind;                      // skiff | kestrel
		FName DockId;                    // the plan's id of the hatch
		FVector Dock = FVector::ZeroVector;            // m, the target's frame: the point on her skin
		FVector DockNormal = FVector(0.0, -1.0, 0.0);  // out of the hull there (the target's frame)
		FVector Bay = FVector::ZeroVector;             // m, the carrier's frame: where it left
		FVector BayNormal = FVector(0.0, -1.0, 0.0);
		float T = 0.f;                   // seconds in this phase
		float AliveT = 0.f;              // seconds since it left
		float HoldT = 0.f;               // seconds waiting off a shield
		float GoneT = 0.f;               // seconds going home without a carrier to go to
		float TransitLimitS = 0.f;       // how long the crossing may take before the boat gives it up (set when it begins: the way there is long or short; 0: not set yet)
		float Side = 1.f;                // which way it goes round a hull that is in its way (+1 or -1)
		bool bDepart = false;            // the host: leave the hull now
		bool bAbort = false;             // the host: turn back
		FVector DockWorldPrev = FVector::ZeroVector;   // (where the hatch was a step ago: its velocity)
		bool bAllowPd = true;            // may point defence fire at it (not while it is latched on the hull)
		bool bPdSilenced = false;        // the boarding drill: no point defence of anybody's fires at this boat (FLaunch::bSilencePd)
	};

	enum class EEventKind : uint8
	{
		Launched,     // out of the bay: the order's craft are on their way
		Docked,       // latched and cut in: the men go aboard
		Destroyed,    // shot down (with its men, if they were aboard), or lost with the ship it was on
		Aborted,      // turned back (a shield held, the target left, the order was withdrawn)
		Departed,     // left the hull after the fight and is going home
		Recovered,    // home: the men (if any) are aboard the carrier again
		Lost          // it could not come home (no carrier): it drifts away
	};
	ASTRA_API const TCHAR* EventName(EEventKind K);

	struct FCraftEvent
	{
		float Time = 0.f;
		EEventKind Kind = EEventKind::Launched;
		int32 CraftId = -1;              // the battle's id of the craft
		int32 Order = -1;
		int32 Leg = 0;
		int32 CarrierId = -1;
		int32 TargetId = -1;
		FName KindKey;
		FString CraftName;               // "Skiff 2"
		int32 Men = 0;                   // aboard at that moment
		bool bMenAboard = false;         // (Destroyed: the men died with it; Recovered: they are home)
		bool bCaptain = false;
		FName DockId;
		FVector Dock = FVector::ZeroVector;
		FVector DockNormal = FVector::ZeroVector;
		FString Cause;                   // Destroyed/Aborted: why, in words ("shot down by the Aquila's point defence")
		bool bTargetGone = false;        // Destroyed: the ship she was latched to is no longer in the battle (a wreck's piece the living space let go of when it drifted out of reach): not a boat that was shot down
		FString CarrierName, TargetName;
	};

	/** One hatch a craft is to latch to: where, in the target's frame. */
	struct FDockPoint
	{
		FVector Local = FVector::ZeroVector;
		FVector Normal = FVector(0.0, -1.0, 0.0);
		FName Id;
	};

	/** What the host asks of the battle: boats to leave a carrier for a target, each for its hatch. */
	struct FLaunch
	{
		int32 CarrierId = -1;
		int32 TargetId = -1;
		FName KindKey;                   // NAME_None: the carrier's own kind
		int32 Order = -1;
		TArray<FDockPoint> Docks;        // one for each craft
		TArray<int32> Men;               // men aboard each (empty: what the kind carries)
		float FirstS = 3.f;              // when the first leaves
		float GapS = 3.f;                // and how long after each one the next
		bool bCaptain = false;           // the Captain is in the first craft
		bool bSilencePd = false;         // the boarding drill: point defence does not fire at these boats (they are flown through it)
	};
	struct FLaunchResult
	{
		bool bOk = false;
		FString Why;                     // the reason, in words, when it is not (or what was cut back)
		int32 Craft = 0;                 // how many were queued
		int32 Men = 0;
		float EtaS = 0.f;                // the first craft's flight, roughly
		FString KindKey;
	};

	/** What the minds are told of a boarding before it is ordered (the facts, not the advice). */
	struct FAssess
	{
		bool bCarrierOk = false;
		FString CarrierWhy;
		FString KindKey;
		int32 BerthsTotal = 0, BerthsFree = 0, MenPerCraft = 0;
		bool bTargetOk = false;
		FString TargetWhy;
		float DistKm = 0.f;
		float EtaS = 0.f;
		bool bTargetDisabled = false;
		int32 PdChannels = 0;
		float PdRangeKm = 0.f;
		float ShieldFrac[6] = {};        // bow, stern, port, starboard, dorsal, ventral (1: full)
		bool bShieldsKnown = false;
		int32 EnemyCraftNear = 0;        // fighters of the target's side within 4 km of it (they shoot at boats)
		float HullFrac = 1.f;
		FString TargetName, CarrierName, TargetClass;
	};

	/** Where one boat is and how long it has to go (the host's, for the minds' picture of an operation under way and for the Captain's screen in the troop bay). */
	struct FBoatStatus
	{
		bool bFound = false;
		FString Name;                    // "Kestrel 1"
		EPhase Phase = EPhase::Idle;
		bool bHome = false;              // going back to the carrier's bay
		bool bDockedOrLatched = false;
		int32 Men = 0;
		double DistM = 0.0;              // to where it is going: her hatch, or the bay's mouth
		double EtaS = 0.0;               // to the way in being cut open (out) or to the bay (home); 0 once it is there
		bool bWaitingOnShield = false;   // held off the hull by a shield: the ETA is only what is left of the approach
	};

	/** What a carrier has: the berths it started with, those that are away, and those lost for good. */
	struct FBay
	{
		int32 Total = 0;
		int32 Away = 0;
		int32 Lost = 0;
		int32 Free() const { return FMath::Max(0, Total - Away - Lost); }
	};

	/** A launch that has been asked for and not made yet. */
	struct FPendingLaunch
	{
		FLaunch Req;
		int32 Index = 0;                 // the next craft of the order
		float T = 0.f;                   // seconds to the next
	};

	/** The truth about one ship of the battle, for the host of the boarding (never for the crew: what the crew may know is the fog of war's). */
	struct FShipFacts
	{
		int32 Id = -1;
		FString ContactId, Name, ClassText;
		FName ClassKey;
		int32 Side = 2;                  // 0 ASTRA, 1 Mandate, 2 neutral
		bool bAlive = false, bDisabled = false, bCraft = false, bPlayer = false, bDerelict = false, bHasModel = false;
		bool bFixture = false;           // a place of the system (a station, a refinery, a mine: SPAZIO-VIVO): not a ship that is fought over, boarded or boarded from
		bool bWreck = false;             // a piece of a ship the war broke (SPAZIO-VIVO, AstraWrecks.h): a fixture and a derelict that the marines may go through (nobody is alive aboard, nobody can be fought for her)
		uint8 WreckSection = 255;        // (a wreck) which part of her it is: 0 the bow, 1 the middle, 2 the stern, 255 her whole hull; her ClassKey is the class of the ship she was
		FVector WreckPivotM = FVector::ZeroVector;   // (a wreck) the pivot the contact's Pos is (what the piece turns about), in the hull's frame (m): a hatch of her plan is at Pos + Att * (its hull place - the pivot)
		int32 WreckSite = -1;            // (a wreck) her record in the space module
		FVector Pos = FVector::ZeroVector;
		FVector Vel = FVector::ZeroVector;
		FQuat Att = FQuat::Identity;
		FVector BoxHalf = FVector::ZeroVector;   // m: the hull as a shot strikes it (zero: a sphere of Radius)
		float BoxMid = 0.f;
		float Radius = 0.f;
		float HullFrac = 1.f;
	};

	/** The facing (0 bow, 1 stern, 2 port, 3 starboard, 4 dorsal, 5 ventral) a hatch looks out of. */
	ASTRA_API int32 FacingOfNormal(const FVector& LocalNormal);

	/** A boarding of the Aquila staged as a drill (ABBORDAGGI-3, `astra.board.drill`): what in today's play stops every boat (the Falcons, the Praetorian's point defence, the shield the crew raises again) is
	 *  held off for the length of one assault so that the lead can watch the boats latch at her airlocks and the fight in her corridors. Plain play is untouched: with no drill every rule is the war's. */
	struct FDrill
	{
		bool bOn = false;
		int32 TargetId = -1;             // the ship whose face is held (the Aquila's)
		int32 Face = -1;                 // the face of her shield that is held at nothing (0 bow, 1 stern, 2 port, 3 starboard, 4 dorsal, 5 ventral); -1: none
		bool bSilencePd = true;          // point defence fires at no boat of the drill, from any ship
		bool bShutDecks = true;          // the flight decks are shut: the squadrons are recalled, none launches
		int32 CarrierId = -1;            // a carrier kept abeam of the target (ParkM from her, on the face's side) with her guns held: the boats' flight is short and the same every time
		double ParkM = 0.0;
		FVector ParkLocal = FVector::ZeroVector;     // where she is kept, in the target's frame (m)
		FQuat ParkRel = FQuat::Identity;             // and how she lies against the target (her boat bay faces the target)
		bool bCarrierHeldFire = false;   // (what the carrier's ceasefire was before: given back at the end)
		float AgeS = 0.f;
	};
}
