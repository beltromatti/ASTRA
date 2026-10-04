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

	bool IsReady() const { return Map.IsValid() && Map->IsReady(); }
	/** A named place: the plan's objective of that name, else the first room of that kind (a plan without hints still has a bridge and an engineering hall). INDEX_NONE if there is none. */
	int32 Objective(const TCHAR* Name, const TCHAR* Kind = nullptr) const;
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
}
