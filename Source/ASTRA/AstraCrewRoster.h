// ASTRA — the Aquila's company: every one of the 560 aboard has a name, a rank, a department, a deck and a home
// (docs/BIBBIA.md: 420 crew, 60 pilots, 80 marines). Generated from a fixed seed, so the same people serve in every
// game. Hits kill and wound real people in the compartment that was struck: every loss has a name.

#pragma once

#include "CoreMinimal.h"

struct FAstraCrewman
{
	FString Rank;
	FString First;
	FString Last;
	FString Dept;          // e.g. "engineering", "flight deck", "marines"
	FString Home;           // home world
	int32 Deck = 1;
	uint8 Status = 0;       // 0 fit, 1 wounded, 2 killed

	FString Name() const { return Rank + TEXT(" ") + First + TEXT(" ") + Last; }
};

class FAstraCrewRoster
{
public:
	void Generate(int32 Seed = 2491);

	/** People caught in a hit on a deck: W wounded, K killed (from that deck, else the nearest ones). Returns
	 *  "Petty Officer Amara Diallo (engineering) killed; Crewman Jonas Berg wounded" (empty if nobody). */
	FString Casualties(int32 Deck, int32 W, int32 K, FRandomStream& R);

	/** A manned aircraft was shot down: its pilot is killed or ejects and is recovered wounded. Returns the report. */
	FString AircrewLost(FRandomStream& R);

	int32 NumWounded() const;
	int32 NumKilled() const;
	/** For the crew's telemetry: counts, and the names of the fallen (most recent first). */
	FString Summary() const;
	const TArray<FAstraCrewman>& Get() const { return People; }

private:
	TArray<FAstraCrewman> People;
	TArray<int32> Fallen;       // in order of loss
	TArray<int32> Hurt;
};
