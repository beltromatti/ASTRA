// ASTRA — DISTRUZIONE: the Aquila's plan (data/ship/aquila_plan.json) as the damage model needs it: every compartment with its volume,
// what it holds, which ways lead out of it (open corridors, doors, section pressure bulkheads, stairs), which of the ship's systems pass
// through it, and a way to find the compartment at a point. Pure data: it loads on a worker thread (like VITA's map) and the model
// (AstraDamageModel.*) and its headless test (AstraDamageSimCommandlet) stand on it. See docs/DISTRUZIONE.md.

#pragma once

#include "CoreMinimal.h"

/** The ship's six power allocations, as the crew sets them (shields, weapons, engines, sensors, life support, flight deck). */
enum class EAstraDmgCategory : uint8 { Shields, Weapons, Engines, Sensors, LifeSupport, FlightDeck, Num };

/** The systems of the plan the model keeps count of (the others, food and water and waste and the like, matter to nothing a fight changes). */
enum class EAstraDmgSystem : uint8 { Reactor, Coolant, Weapons, Ordnance, Sensors, DataTrunk, LifeSupport, Catapults, PowerBus, Engines, DamageControl, Num };

/** What a kind of room holds, as fire, blast and electricity see it: the numbers the model reads (tuned in AstraDamageMap.cpp). */
struct FAstraDmgProfile
{
	float Ignite = 0.8f;       // how readily it takes fire (1: a cabin's bedding and plastics)
	float Fuel = 100.f;        // seconds of a full fire the room can feed
	float Hard = 150.f;        // the energy of a blow its fabric takes before it is wrecked
	float Conduit = 0.6f;      // how thick the power runs there: how much of a blow becomes power lost
	float Fill = 0.4f;         // the share of a blow the room swallows (the rest travels on)
	float Traffic = 1.f;       // how often its doors stand open
	bool bSuppress = false;    // fixed fire suppression (machinery, magazines, the hangar)
	bool bExplosive = false;   // a magazine: a fire that is let burn goes off
};

/** A way out of a compartment into another. */
struct FAstraDmgLink
{
	enum class EKind : uint8 { Open, Door, Blast, Stair, Lift };
	int32 To = INDEX_NONE;
	int32 Door = INDEX_NONE;       // index into the map's doors (Door and Blast), else INDEX_NONE
	float AreaM2 = 1.f;            // the opening, when it is open
	EKind Kind = EKind::Open;
	FVector AtCm = FVector::ZeroVector;   // where it is (world cm): the way out, for one who must leave
};

struct FAstraDmgDoor
{
	FName Id;
	FName Kind;                    // door | gate | blast | sliding
	int16 Deck = 0;
	FVector PosCm = FVector::ZeroVector;
	float Yaw = 0.f;
	float WidthM = 1.6f, HeightM = 2.4f;
	bool bBlast = false;           // a section's pressure bulkhead
	TCHAR SecAft = TEXT('A'), SecFwd = TEXT('A');   // blast: the sections either side
	int32 A = INDEX_NONE, B = INDEX_NONE;           // the compartments either side
};

struct FAstraDmgComp
{
	FName Id;
	FString Name;                  // "Main Galley" (a corridor's: "Spine")
	FName Kind;
	TCHAR Section = TEXT('A');
	int16 Deck = 0;
	int16 DeckLo = 0, DeckHi = 0;  // the decks it spans (a hall is tall)
	FName Dept;
	uint8 Status = 0;              // 0 planned (no geometry yet), 1 built, 2 existing
	FBox Box = FBox(ForceInit);    // world cm
	float VolumeM3 = 100.f;
	float FloorM2 = 30.f;
	uint8 Profile = 0;             // index into the map's profiles
	bool bCorridor = false;
	bool bHall = false;
	TArray<FAstraDmgLink> Links;
	TArray<uint8> Systems;         // EAstraDmgSystem values it hosts
	int32 Crew = 0;                // the people it holds at work (the plan's crew_slots), for how busy its doors are
};

/** A deck: its floor, its sections along the ship and its half width where (the envelope the plating follows). */
struct FAstraDmgDeck
{
	int32 Id = 0;
	float FloorCm = 0.f;
	float ClearCm = 380.f;
	float XFwdCm = 0.f, XAftCm = 0.f;
	TArray<FVector2D> HalfWidth;   // (x, half width), world cm, from the bow aft
	float HalfWidthAt(float XCm) const;
};

class FAstraDamageMap
{
public:
	TArray<FAstraDmgComp> Comps;
	TArray<FAstraDmgDoor> Doors;
	TArray<FAstraDmgDeck> Decks;               // by deck number from 1 (Decks[0] is deck 1)
	TArray<FAstraDmgProfile> Profiles;
	TMap<FName, int32> CompByName;
	TMap<FName, int32> DoorByName;
	TArray<int32> BlastDoors;                  // the section pressure bulkheads (indices into Doors)
	/** The compartments that host each of the ship's power allocations' systems, and how many host each system (for the share a loss is). */
	TArray<int32> Hosts[(int32)EAstraDmgSystem::Num];
	/** The ship's volume in the plan's frame (cm): where the decks lie. */
	FBox Hull = FBox(ForceInit);

	/** Reads the plan (the staged copy first, the repository's when bRepoFirst is false and there is none: the bench passes true). False (and a reason) when it is missing or does not parse. Safe on a worker thread. */
	bool Load(FString& OutError, bool bRepoFirst = false);
	/** Reads a plan from a path (the Aquila's, or a class's: data/ship/plans/<class>.json). The real body of the loader; the one above is the Aquila's path with this. (Same as FLOTTA-VIVA's: one loader.) */
	bool Load(const FString& Path, FString& OutError);
	/** Where the plan's origin is in the hull's frame (m): the Aquila's is the bridge floor (172, 0, 62 in her mesh's frame); a class plan written in its hull frame says (0, 0, 0) with "origin_in_hull". */
	FVector OriginInHullM = FVector(172.0, 0.0, 62.0);

	/** The smallest compartment containing a point (world cm), within Slack cm of its walls; INDEX_NONE outside every one. */
	int32 CompartmentAt(const FVector& Cm, float SlackCm = 0.f) const;
	const FAstraDmgDeck* DeckById(int32 Id) const { return Id >= 1 && Id <= Decks.Num() ? &Decks[Id - 1] : nullptr; }
	/** The deck whose floor is just under a height (world cm), or 0. */
	int32 DeckAtZ(float ZCm) const;
	/** The decks' top (the ceiling of the highest deck of the hull's body, not the bridge island's) and the keel's floor (world cm). */
	float BodyTopCm() const { return TopCm; }
	float KeelCm() const { return KeelFloorCm; }
	/** A short place name for a report: "deck 4 section B (Main Galley)". */
	FString Describe(int32 Comp) const;
	/** The plan's door standing within RadiusCm of a point (world cm): the nearest, or INDEX_NONE (how a door actor of the level is matched to its door). */
	int32 DoorNear(const FVector& Cm, float RadiusCm) const;
	const FAstraDmgProfile& ProfileOf(int32 Comp) const { return Profiles[Comps[Comp].Profile]; }
	const TCHAR* CategoryName(EAstraDmgCategory C) const;

private:
	static constexpr float CellCm = 1000.f;
	int32 GridX0 = 0, GridY0 = 0, GridNX = 0, GridNY = 0;
	TArray<TArray<int32>> Grid;
	TMap<int64, TArray<int32>> DoorGrid;           // the doors by 2 m cell
	static constexpr float DoorCellCm = 200.f;
	static int64 DoorCell(int32 X, int32 Y, int32 Z) { return ((int64)(X + 4096) << 40) | ((int64)(Y + 4096) << 20) | (int64)(Z + 4096); }
	float TopCm = 0.f, KeelFloorCm = 0.f;
	void BuildGrid();
};
