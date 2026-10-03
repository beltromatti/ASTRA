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
		float Cruise;                    // m/s
		float Accel;                     // m/s^2
		float PdHit;                     // the chance that a point-defence shot finds it (a fighter's is 0.07 to 0.14): an armoured boat, slower, but a hull of 140 to 200
		float PdDamage;                  // and what a hit does
		float LatchS;                    // from touching the hull to the cut: seconds
	};

	/** The two kinds. */
	ASTRA_API const FKind& Skiff();
	ASTRA_API const FKind& Kestrel();
	ASTRA_API const FKind* KindByKey(FName Key);

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
		float Side = 1.f;                // which way it goes round a hull that is in its way (+1 or -1)
		bool bDepart = false;            // the host: leave the hull now
		bool bAbort = false;             // the host: turn back
		FVector DockWorldPrev = FVector::ZeroVector;   // (where the hatch was a step ago: its velocity)
		bool bAllowPd = true;            // may point defence fire at it (not while it is latched on the hull)
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
}
