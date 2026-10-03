// ASTRA — ABBORDAGGI-2: a boarding as a set of people on a ship's plan (docs/brief/ABBORDAGGI-2.md §2, §4).
//
// The simulation (AstraBoardSim.*) fights; this puts the people in it: the holders of a ship at the posts her plan says (the bridge crew, the engineering watch, the guard of the
// commander's suite, the armoury, the medbay, the comms room, the boat crews) and a few roaming the berthing decks who answer the alarm, and the attackers at the dock they came in by
// with their objective. Plain code over a plan (no actors, no world): the game's host uses it for the fights it does not make bodies for, and the bench for the whole of them.

#pragma once

#include "CoreMinimal.h"
#include "AstraBoardPlans.h"
#include "AstraBoardSim.h"

namespace AstraBoardScene
{
	struct FSpec
	{
		AstraBoard::ESide Attacker = AstraBoard::ESide::Aquila;     // who comes aboard (the other side holds the ship)
		int32 Dock = INDEX_NONE;                                    // the plan's dock they cut in at (INDEX_NONE: the first)
		int32 Breach = INDEX_NONE;                                  // or a compartment (it wins over the dock)
		FString Objective = TEXT("captain");                        // bridge | engineering | captain | armory | medbay | brig | comms | hangar, or a compartment's id
		int32 Attackers = 24;
		int32 PerSquad = 6;
		float FirstAtS = 25.f;                                      // when the first of them is through (the craft's latch, the cut)
		float PostShare = 0.8f;                                     // the share of each post's men on their feet and armed
		int32 Roaming = 8;                                          // the others who answer the alarm (from the berthing decks)
		float SealedShare = 0.3f;                                   // the share of the pressure bulkheads shut when they come
		bool bSweep = true;                                         // they also win by putting the holders down
		bool bShipSensors = false;                                  // the holders' ship sees her own corridors (a ship with power)
		int32 Seed = 1;
	};
	struct FResult
	{
		bool bOk = false;
		FString Why;
		int32 Objective = INDEX_NONE;
		int32 Breach = INDEX_NONE;
		FVector BreachPos = FVector::ZeroVector;
		TArray<int32> AttackSquads, DefendSquads;
		int32 Defenders = 0;
		FString ObjectiveName;
	};

	/** Fills a sim (made with Init on the plan's map) with the holders at their posts and the attackers at the dock. */
	ASTRA_API FResult Build(FAstraBoardSim& Sim, const FBoardShipPlan& Plan, const FSpec& Spec);
}
