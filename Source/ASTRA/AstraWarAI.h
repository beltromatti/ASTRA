// ASTRA — the war's hierarchy (docs/GUERRA.md, F2.2): battle groups of warships, flights of craft, the grid that answers
// "who is near", and the data the AI keeps. The code that runs them is AstraWarGroups.cpp (groups, fleets), AstraWarShipAI.cpp
// (one warship), AstraWarCraft.cpp (flights and craft), AstraWarKnowledge.cpp (what each side knows).

#pragma once

#include "CoreMinimal.h"
#include "AstraWarTypes.h"

// (the enum is declared in AstraBattleSubsystem.h, where its UENUM lives; AstraSideIdx() is defined there too)
enum class EAstraSide : uint8;

/** How a battle group holds itself. */
enum class EAstraFormation : uint8
{
	Line,      // abreast, across the line to the enemy
	Wedge,     // a V, the leader at the point
	Column,    // in single file behind the leader
	Screen     // an arc between the enemy and a ship it protects
};

/** Where a group is in its battle. */
enum class EAstraGroupState : uint8
{
	Engage,    // moving to and holding its range, fighting
	Withdraw,  // breaking off in order
	Regroup    // reforming at a rally point after a withdrawal
};

/** The order in force on a group (docs/GUERRA.md: the menu of the minds). */
enum class EAstraGroupOrder : uint8
{
	Auto,        // the group's own judgement
	Attack,      // concentrate on one ship or one enemy group
	Pin,         // keep them busy at long range without closing (a holding attack)
	FlankLeft,   // swing round the enemy's left (as it faces us) and strike its beam
	FlankRight,
	Screen,      // fall back around the ship it protects
	Withdraw,    // break off
	Regroup,     // stop and reform where it stands
	Reinforce,   // go to another group's aid
	Hold         // hold position, fire at what comes in range
};

/** What a warship has been asked to do by its group this moment. */
enum class EAstraTask : uint8
{
	Formation,   // its slot in the group's formation
	Flank,       // a point on the enemy's beam or quarter
	Reserve,     // behind the line, recovering (a rotation)
	RearGuard    // covering a withdrawal
};

/** A battle group: a handful of warships that fight as one (formation, target allocation, flanks, rotation, missile
 *  saturation, retreat and regroup). A fleet is all the groups of a side. */
struct FAstraBattleGroup
{
	int32 Id = -1;
	EAstraSide Side;
	FString Name;
	TArray<int32> Members;           // ship ids (warships)
	int32 LeaderId = -1;
	int32 ProtecteeId = -1;          // the ship it screens (the Aquila, a carrier, a flagship): -1 none
	EAstraFormation Formation = EAstraFormation::Line;
	EAstraGroupState State = EAstraGroupState::Engage;
	// the order in force (mode + parameters + expiry), as the stations' modes are
	EAstraGroupOrder Order = EAstraGroupOrder::Auto;
	int32 OrderShip = -1;            // Attack/Pin/Flank: the ship id the order is about (-1: the group's own choice)
	int32 OrderGroup = -1;           // Attack/Pin/Reinforce: the group id
	float OrderUntil = -1.f;         // battle time it lapses (-1: until changed)
	FString OrderBy;                 // who gave it: admiral | captain | auto
	// what it sees and wants
	FVector Centroid = FVector::ZeroVector;
	FVector Vel = FVector::ZeroVector;
	FVector Axis = FVector::ForwardVector;    // to the enemy
	FVector Guide = FVector::ZeroVector;      // the formation guide: a point that moves ahead of the group
	bool bGuideSet = false;
	FVector Objective = FVector::ZeroVector;  // where it goes when it sees nothing
	bool bHasObjective = false;
	int32 EnemyGroup = -1;           // the enemy group it is assigned to (fleet level)
	int32 FocusTarget = -1;          // the ship id under concentrated fire
	float FocusSince = 0.f;
	float EngageRange = 5500.f;      // m: the range its armament likes against this enemy
	// strength and spirit
	float StartStrength = 0.f, Strength = 0.f, EnemyStrength = 0.f;
	int32 StartCount = 0;
	float Morale = 1.f;
	float WeakSince = -1.f;          // the time the balance turned against it (a retreat needs it to last)
	FVector Rally = FVector::ZeroVector;
	float RegroupSince = 0.f;
	float WithdrawSince = 0.f;
	// coordinated missiles
	float SalvoTOT = -1.f;           // the time the salvo lands (each ship launches at TOT minus its flight time)
	float LastSalvo = -100.f;
	int32 FlankShip[2] = {-1, -1};
	int8 FlankSide[2] = {0, 0};
	float FlankAssignedAt = -100.f;
	float NextThink = 0.f;
};

/** A flight of 2-4 craft (a leader and wingmen), the unit that flies a mission. */
struct FAstraFlight
{
	int32 Id = -1;
	int32 Squadron = -1;             // index in Squadrons (carrier wing -> squadron -> flight -> craft)
	EAstraSide Side;
	TArray<int32> Members;           // craft ids, the leader first
	int32 LeaderId = -1;
	int32 TargetId = -1;             // what the mission is about (a warship id)
	int32 Bandit = -1;               // the enemy craft the flight has claimed
	uint8 Phase = 0;                 // 0 forming up, 1 transit/patrol, 2 attack, 3 egress, 4 returning to base
	float PhaseT = 0.f;
	FVector Waypoint = FVector::ZeroVector;
	FVector RunDir = FVector::ForwardVector;
	float NextThink = 0.f;
};

/** A uniform grid over the craft and warships, rebuilt every tick: the proximity questions (point defence, separation, who is
 *  near) cost what is near, not what exists. Cells are 2.5 km. */
struct FAstraWarGrid
{
	static constexpr float Cell = 2500.f;
	TMap<uint64, int32> Head;         // cell key -> first entry
	TArray<int32> Next;               // entry chain: an index in Ships
	void Reset(int32 N)
	{
		Head.Reset();
		Next.SetNumUninitialized(N, EAllowShrinking::No);
	}
	static uint64 Key(int64 X, int64 Y, int64 Z)
	{
		return ((uint64)(X + 1048576) << 42) | ((uint64)(Y + 1048576) << 21) | (uint64)(Z + 1048576);
	}
	static int64 CellOf(double V) { return (int64)FMath::FloorToDouble(V / Cell); }
	void Add(int32 Index, const FVector& P)
	{
		const uint64 K = Key(CellOf(P.X), CellOf(P.Y), CellOf(P.Z));
		const int32* H = Head.Find(K);
		Next[Index] = H ? *H : -1;
		Head.Add(K, Index);
	}
	/** Calls Fn(index) for every entry in the cells the sphere (P, R) touches (a superset: test the distance yourself). */
	template <typename Func>
	void Query(const FVector& P, double R, Func&& Fn) const
	{
		const int64 X0 = CellOf(P.X - R), X1 = CellOf(P.X + R), Y0 = CellOf(P.Y - R), Y1 = CellOf(P.Y + R), Z0 = CellOf(P.Z - R), Z1 = CellOf(P.Z + R);
		for (int64 X = X0; X <= X1; ++X)
		{
			for (int64 Y = Y0; Y <= Y1; ++Y)
			{
				for (int64 Z = Z0; Z <= Z1; ++Z)
				{
					const int32* H = Head.Find(Key(X, Y, Z));
					for (int32 I = H ? *H : -1; I >= 0; I = Next[I])
					{
						Fn(I);
					}
				}
			}
		}
	}
};
