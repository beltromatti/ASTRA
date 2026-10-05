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
struct FFleetCasualty;                // ... and what a landing did to her people (the books)

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
	/** A place of the plan by a name the minds and the commands use (bridge, engineering, captain, armory, medbay, brig, comms, hangar, or a room's id): the room, and what it is called in a report (INDEX_NONE: the plan has none; a
	 *  piece of a ship has only the places she still has). */
	ASTRA_API int32 ObjectiveOf(const FBoardShipPlan& Plan, const FString& Name, FString& OutLabel);

	/** What was left aboard a piece of a broken ship (ABBORDAGGI-4), as the boarding wants it: SPAZIO-VIVO's record of her (AstraWrecks.h FAboard) copied when the order is given, so that nothing of the living space is held
	 *  while the marines are aboard. */
	struct FWreckAboard
	{
		FString Name;                                               // what she was ("ASN Vigilant")
		int32 Complement = 0;                                       // the people her class carries
		int32 Killed = 0;                                           // who died of the blows before she went (where they fell)
		int32 Lost = 0;                                             // who was alive and was lost with her
		int32 Escaped = 0;                                          // who got away in the lifepods
		float Share = 1.f;                                          // the share of her people who lie in this piece (her structure's share: the war's table)
		struct FRoom
		{
			int32 Comp = INDEX_NONE;
			float Air = 1.f, Hole = 0.f, Fire = 0.f, Smoke = 0.f, Heat = 0.f, Power = 1.f, Wreck = 0.f;
			bool bGutted = false, bLocked = false;
		};
		TArray<FRoom> Rooms;                                        // the rooms as they were a moment after the loss (a room not listed is as built)
		TArray<FName> SealedDoors;                                  // the pressure bulkheads that were shut
		/** The dead in this piece: of those who died before she went and of those lost with her, her share. */
		int32 DeadHere() const { return FMath::Clamp(FMath::RoundToInt(Share * (float)(Killed + Lost)), 0, 60); }
	};
	/** The inside of a wreck's piece as the scene builder takes the war's picture of a ship: her rooms as the record has them (the ones of the piece), her shut bulkheads, nobody alive, and her dead laid where people are
	 *  (the rooms that hold her crew at work, deterministic for the seed). */
	ASTRA_API void WreckInside(const FBoardShipPlan& Plan, const FWreckAboard& Aboard, int32 Seed, FFleetSnapshot& Out);
	/** A ship that has lost her power (and her fight): her marines and the guard of her hatches stand to (half of them), a few of the rest take up arms; the people at dead consoles in the dark have nothing left to
	 *  fight for. bFromWar: the war's own picture of her inside is the scene (her people are where the war left them); without it she is a derelict nobody fought through (no record of her crew: a post may be left
	 *  empty, nobody roams). The host and the bench come to this one place for the numbers, so that what the bench measures is what the game does. */
	ASTRA_API void ForDisabledShip(FSpec& Spec, bool bFromWar);

	/** What a fight did to the people of one side (ABBORDAGGI-3), as the books of the ship that side belongs to want them: every man who is dead (killed, or lost with his boat), and every man who is hurt (down on the
	 *  deck, or carried off alive). A defender who came from the war's picture of her carries his place in her books (FUnit::Person); any other is placed by the room where he fell. The attackers have no room on the ship
	 *  they landed on: they are the carrier's marines. The Captain and the Aquila's roster marines are not here (the roster has its own books). The host writes them to the battle (FleetBoardingResult) and the bench to an interior. */
	ASTRA_API void CasualtiesOf(const FAstraBoardSim& Sim, AstraBoard::ESide Side, TArray<FFleetCasualty>& Out);
}
