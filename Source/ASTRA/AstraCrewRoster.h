// ASTRA — the Aquila's company: every one of the 560 aboard has a name, a rank, a department, a deck and a home
// (docs/BIBBIA.md: 420 crew, 60 pilots, 80 marines). Generated from a fixed seed, so the same people serve in every
// game. Hits kill and wound real people in the compartment that was struck: every loss has a name. The wounded go to
// the Medbay (Deck 6): each has an injury from what hit them, a condition that changes as the doctors work, and a bed.

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
	bool bFemale = false;
	// in the Medbay
	FString Injury;         // "second-degree burns on the arms and hands"
	uint8 Condition = 0;    // 0 stable, 1 serious, 2 critical
	int32 Bed = -1;         // 0..NumBeds-1, or -1: on a cot in the passage (the ward is full)
	float CareMinutes = 0.f;   // time in the present condition

	FString Name() const { return Rank + TEXT(" ") + First + TEXT(" ") + Last; }
	const TCHAR* ConditionName() const { return Condition >= 2 ? TEXT("critical") : (Condition == 1 ? TEXT("serious") : TEXT("stable")); }
};

class FAstraCrewRoster
{
public:
	static constexpr int32 NumBeds = 12;

	void Generate(int32 Seed = 2491);

	/** People caught in a hit on a deck: W wounded, K killed (from that deck, else the nearest ones); Cause is what hit
	 *  the compartment ("hull breach", "fire", "conduit damage") and shapes the injuries. Returns
	 *  "Petty Officer Amara Diallo (engineering) killed; Crewman Jonas Berg wounded" (empty if nobody). Present: who is
	 *  physically in that compartment now (VITA's RosterIn), taken first; the deck's people after them. */
	FString Casualties(int32 Deck, int32 W, int32 K, FRandomStream& R, const FString& Cause = FString(), const TArray<int32>* Present = nullptr);

	/** A manned aircraft was shot down: its pilot is killed or ejects and is recovered wounded. Returns the report. */
	FString AircrewLost(FRandomStream& R);

	/** The ship is abandoned and K people do not get off: first the critically wounded who could not be moved, then
	 *  the engineers holding the reactor to the end (Deck 7), then anyone. Returns "Petty Officer ... (Engineering),
	 *  Crewman ... and 23 others" (empty if nobody). The wounded who got off stay wounded (the ward goes with them). */
	FString LostWithShip(int32 K, FRandomStream& R);

	/** The Medbay's work over Minutes of care: conditions improve (or, for the critical, sometimes fail), the healed go
	 *  back to duty. Each change is reported in OutNews (bReport = the Captain should hear it). */
	struct FNews { FString Text; bool bReport = false; };
	void Care(float Minutes, FRandomStream& R, TArray<FNews>& OutNews);

	/** For the campaign save: who fell, who is in the medbay (indices into the seeded roster), and the medbay's
	 *  details (injury, condition, bed) of each wounded. */
	const TArray<int32>& GetFallen() const { return Fallen; }
	const TArray<int32>& GetHurt() const { return Hurt; }
	void Restore(const TArray<int32>& InFallen, const TArray<int32>& InHurt);
	void RestoreCare(int32 Index, const FString& Injury, uint8 Condition, int32 Bed);

	int32 NumWounded() const;
	int32 NumKilled() const;
	/** For the crew's telemetry: counts, and the names of the fallen (most recent first). */
	FString Summary() const;
	const TArray<FAstraCrewman>& Get() const { return People; }
	/** Who lies in a bed (index into Get()), or -1. */
	int32 InBed(int32 Bed) const;
	/** Changes whenever someone is admitted, moves, changes condition or leaves (the ward's visuals follow it). */
	int32 Version() const { return Rev; }

private:
	TArray<FAstraCrewman> People;
	TArray<int32> Fallen;       // in order of loss
	TArray<int32> Hurt;
	int32 Rev = 0;
	void Admit(int32 Index, const FString& Injury, uint8 Condition);
	void Leave(int32 Index);
	int32 FreeBed() const;
};
