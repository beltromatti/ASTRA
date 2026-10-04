// ASTRA — ABBORDAGGI-2: a boarding as a set of people on a ship's plan (docs/brief/ABBORDAGGI-2.md §2, §4).
//
// The simulation (AstraBoardSim.*) fights; this puts the people in it: the holders of a ship at the posts her plan says (the bridge crew, the engineering watch, the guard of the
// commander's suite, the armoury, the medbay, the comms room, the boat crews) and a few roaming the berthing decks who answer the alarm, and the attackers at the dock they came in by
// with their objective. Plain code over a plan (no actors, no world): the game's host uses it for the fights it does not make bodies for, and the bench for the whole of them.

#pragma once

#include "CoreMinimal.h"
#include "AstraBoardPlans.h"
#include "AstraBoardSim.h"

struct FFleetSnapshot;                // FLOTTA-VIVA (AstraFleetInterior.h): what the war has left of a ship's inside

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
		/** What the war has left of the ship's inside: her people alive and where they stand (the fit who take up arms, the wounded who lie), the pressure bulkheads she has shut. With it the holders are
		 *  those people, and the bulkheads those; without it (a ship the war never hit through her plating) the plan's garrison and a share of the bulkheads at random. */
		const FFleetSnapshot* Inside = nullptr;
		float GuardShare = -1.f;                                    // the share of the ship's marines and the guard of her hatches (posts of role marines, marines_dock) who are on their feet and armed: -1 is PostShare's; with Inside 0.9
		int32 MinPerPost = 1;                                       // a post is manned by at least this many (0: a post may be left empty: a derelict)
		int32 MaxDefenders = 340;                                   // (with Inside) the most who fight: a crew of a thousand does not all take up arms (and the simulation's step grows with the men in it)
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
		// (with Inside) what the war's picture of her inside gave the scene
		bool bFromWar = false;
		int32 Wounded = 0;                                          // lying on her decks, alive
		int32 Unarmed = 0;                                          // fit, and not among those who fight (they keep to their stations or hide)
		int32 ShutBulkheads = 0;
		bool bCaptainAlive = false;
	};

	/** Fills a sim (made with Init on the plan's map) with the holders at their posts and the attackers at the dock. */
	ASTRA_API FResult Build(FAstraBoardSim& Sim, const FBoardShipPlan& Plan, const FSpec& Spec);
	/** A ship that has lost her power (and her fight): her marines and the guard of her hatches stand to (half of them), a few of the rest take up arms; the people at dead consoles in the dark have nothing left to
	 *  fight for. bFromWar: the war's own picture of her inside is the scene (her people are where the war left them); without it she is a derelict nobody fought through (no record of her crew: a post may be left
	 *  empty, nobody roams). The host and the bench come to this one place for the numbers, so that what the bench measures is what the game does. */
	ASTRA_API void ForDisabledShip(FSpec& Spec, bool bFromWar);
}
