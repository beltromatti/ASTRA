// ASTRA — ABBORDAGGI-2: the plan of a ship that is boarded (docs/brief/ABBORDAGGI-2.md §3).
//
// The Aquila's plan (data/ship/aquila_plan.json) is read by the damage model and the soldiers' map is built from it (UAstraBoardSubsystem). Any other ship is fought over on the plan of
// her class: data/ship/plans/<class>.json (FLOTTA-VIVA's, the format of the Aquila's, the same file their insides stand on: the war's rooms and the boarding's are the same rooms in the same
// order). One loader reads it: FAstraDamageMap::Load(Path) (the same as FLOTTA-VIVA's), then the soldiers' map is built on it, and the parts of the file that only boarding reads (the docks on
// the skin, where the crew stands, the named places) are kept beside it.
//
// Plain code (no actors, no world): the bench loads every class and fights over it headless.

#pragma once

#include "CoreMinimal.h"
#include "AstraBoardMap.h"
#include "AstraDamageMap.h"

/** How a room is as the war left it (a ship that has been fought over): its power, its fire and smoke, its air, whether its structure is gone. A room that is not listed is as built. */
struct FBoardRoomMood
{
	float Power = 1.f, Fire = 0.f, Smoke = 0.f, Air = 1.f;
	bool bGutted = false;
	bool Dark() const { return Power < 0.45f || bGutted; }
	bool Burns() const { return Fire >= 0.10f && !bGutted; }
};

namespace AstraBoardDress { struct FLayout; }

/** A ship's plan as boarding uses it. */
struct ASTRA_API FBoardShipPlan
{
	FName Class;
	FString Label;
	FString Path;
	FString Style;                                  // whose ship she is: mandate | astra | guild (the plan's "style": her decks are dressed in her side's hand)
	TSharedPtr<AstraBoardDress::FLayout> Layout;    // the props of her rooms (AstraBoardDress::MakeLayout), from the plan alone; null for the Aquila
	TSharedPtr<FAstraDamageMap> Dmg;
	TSharedPtr<FAstraBoardMap> Map;
	/** A hatch on the skin where a craft latches and the breach opens into Comp: in the plan's frame (cm). */
	struct FDock
	{
		FName Id;
		int32 Comp = INDEX_NONE;
		FName Face;                                 // port | starboard | dorsal | ventral | bow | stern
		FName Kind;                                 // hatch (a boat latches to it and the boarders cut in) | mouth (where the ship's own boats leave: not a way in)
		FVector Pos = FVector::ZeroVector;          // on the skin (the room it opens into may stand a little inside it)
		FVector Normal = FVector::ZeroVector;       // out of the hull
		int32 Deck = 0;
	};
	/** Where some of the ship's people stand when she is held (the plan's own hint; the class's roster may replace it). */
	struct FPost
	{
		int32 Comp = INDEX_NONE;
		int32 N = 0;
		FString Role;
	};
	TArray<FDock> Docks;
	TArray<FPost> Garrison;
	TMap<FName, int32> Objectives;                  // bridge, engineering, captain, armory, medbay, brig, comms, hangar -> a compartment
	int32 Crew = 0;                                 // the people of the class aboard when she is whole
	// --- a piece of her (ABBORDAGGI-4: a wreck's section is boarded): the rooms of one part of the hull, cut off from the rest at the war's cut planes
	float CutBowCm = 0.f, CutSternCm = 0.f;         // the class's two cut planes in the plan's frame (cm): the war's bow is beyond the first, her stern beyond the second (both zero: thirds of the hull)
	uint8 Section = 255;                            // 0 the bow, 1 the middle, 2 the stern, 255 the whole ship
	TArray<uint8> Present;                          // (a piece) by room: 1 when it is part of the piece; empty: every room is
	bool Has(int32 Comp) const { return Present.IsEmpty() || (Present.IsValidIndex(Comp) && Present[Comp] != 0); }
	/** The war's section of a room (FLOTTA-VIVA's rule: the middle of its box against the cut planes; with no cuts, the hull's thirds). */
	uint8 SectionOf(int32 Comp) const;

	bool IsReady() const { return Map.IsValid() && Map->IsReady(); }
	/** A named place: the plan's objective of that name, else the first room of that kind (a plan without hints still has a bridge and an engineering hall); of a piece, only the rooms she has. INDEX_NONE if there is none. */
	int32 Objective(const TCHAR* Name, const TCHAR* Kind = nullptr) const;
	/** The number of rooms of the piece (of the whole ship: all). */
	int32 NumRooms() const;
	/** A room of a piece whose end wall stands at one of her torn ends (within MarginCm of a cut plane): open to space. False for the whole ship. */
	bool AtTornEnd(int32 Comp, float MarginCm) const;
	/** Between the plan's frame (cm) and the hull's (m): the damage map says where the plan's origin stands in the hull. */
	FVector OriginInHullM() const { return Dmg.IsValid() ? Dmg->OriginInHullM : FVector::ZeroVector; }
	FVector PlanToHullM(const FVector& PlanCm) const { return PlanCm / 100.0 + OriginInHullM(); }
	FVector HullToPlanCm(const FVector& HullM) const { return (HullM - OriginInHullM()) * 100.0; }
	/** The dock nearest to a point of the hull (m), or INDEX_NONE. */
	int32 NearestDock(const FVector& HullM) const;
};

namespace AstraBoardPlans
{
	/** Where a class's plan is: the staged copy (Content/ASTRA/Data/plans/<class>.json), else the repository's (data/ship/plans/<class>.json): FLOTTA-VIVA's resolver, so the war's picture of a ship and the
	 *  boarding's plan are the same file. Empty when there is none. */
	ASTRA_API FString PathFor(FName ClassKey);
	/** Reads and builds the plan of a class (kept: the second boarding of the same class costs nothing). Safe on a worker thread. */
	ASTRA_API TSharedPtr<FBoardShipPlan> Load(FName ClassKey, FString& OutWhy);
	/** The plan of a class if it has been read already (nothing is read: the game thread asks this before it hands the reading to a worker). */
	ASTRA_API TSharedPtr<FBoardShipPlan> Peek(FName ClassKey);
	/** The same for a file (the bench's; not kept). */
	ASTRA_API TSharedPtr<FBoardShipPlan> LoadFile(const FString& Path, FName ClassKey, FString& OutWhy);
	/** The classes that have a plan (the file names in the plan directory). */
	ASTRA_API void ClassesWithPlans(TArray<FName>& Out);
	/** The key a piece of a class is kept under ("vigilant#2": the stern section); the whole ship's is her class. */
	ASTRA_API FName KeyOfPiece(FName ClassKey, uint8 Section);
	/** The plan of one piece of a class (a section of a wreck, 0 bow, 1 middle, 2 stern; 255 or more is the whole ship, the class's own plan): her rooms on the one side of the cuts and no way across them, the hatches
	 *  she still has and a torn end for each cut face (a boat latches at the torn end, the boarders cut in at its wall), the places of the plan she still has. Kept, like the whole ship's. Safe on a worker thread. */
	ASTRA_API TSharedPtr<FBoardShipPlan> LoadPiece(FName ClassKey, uint8 Section, FString& OutWhy);
	/** Where the marines go in a piece that has no commander to seize: her bridge if she still has it, else her engineering hall, else the commander's quarters, else the room furthest from where they cut in (a walk through
	 *  all of her). INDEX_NONE for a plan with no room. */
	ASTRA_API int32 PieceObjective(const FBoardShipPlan& Plan, int32 CutInComp);
}
