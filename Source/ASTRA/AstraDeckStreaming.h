// ASTRA — the decks of the Aquila stream in and out as the Captain walks the ship (docs/NAVE.md §7bis). Each built deck is a sub-level of L_Bridge
// (/Game/ASTRA/Maps/Decks/L_Deck05 ... a ULevelStreamingDynamic that starts unloaded) holding the deck's shell (AAstraDeckShell: the instanced modules and
// rooms), its doors and nothing else; this subsystem keeps loaded the deck the Captain is on and the decks a stair column joins it to, drops the others
// after a while, and tells the lift when the deck it is about to open on is ready.
//
// The bridge's complex, the older rooms (Mess Hall, Crew Berthing, Medbay, Main Engineering, Flight Deck) and the sky stay in the persistent level.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "AstraDeckStreaming.generated.h"

class ULevelStreaming;
class UAstraShipPlan;

UCLASS()
class ASTRA_API UAstraDeckStreaming : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UAstraDeckStreaming, STATGROUP_Tickables); }

	/** The decks that have a sub-level in this world, ascending. */
	TArray<int32> BuiltDecks() const;

	/** Asks for the deck at a world position (cm) and the decks its stairs join it to, and keeps them for HoldS seconds even if the Captain is not
	 *  there: the lift's destination, a teleport. A level that is already in the world costs nothing. */
	void RequestAt(const FVector& WorldCm, float HoldS = 30.f);
	void RequestDeck(int32 Deck, float HoldS = 30.f);

	/** True when the deck at that point has its level in the world and visible (a deck with no sub-level is always ready: nothing to wait for). */
	bool IsReadyAt(const FVector& WorldCm) const;
	bool IsDeckReady(int32 Deck) const;

	/** The lift's last resort when the destination is not ready by the time the car arrives: loads it NOW, blocking, while the screen is dark. Returns
	 *  true when it is ready afterwards. */
	bool ForceReadyAt(const FVector& WorldCm);

	/** The decks wanted when the Captain stands on `Deck` (in a hall of an existing room or not): the deck itself and, outside a hall, the decks a stair
	 *  column joins it to. Pure (the plan only): the tests use it. */
	static TArray<int32> DecksFor(const UAstraShipPlan& Plan, int32 Deck, bool bInHall);

	/** The tests' Captain: no pawn needed. */
	void SetTestPosition(const FVector& FeetCm) { bTestPos = true; TestFeet = FeetCm; }

	/** One line a deck for astra.decks. */
	FString Describe() const;

private:
	struct FDeckLevel
	{
		TWeakObjectPtr<ULevelStreaming> Level;
		double LastWanted = -1.0e9;      // world time the deck was last needed
		double HoldUntil = 0.0;          // a request keeps it until then
		bool bPinned = false;            // astra.decks.pin
	};
	TMap<int32, FDeckLevel> Levels;
	float Accum = 0.f;
	bool bTestPos = false;
	FVector TestFeet = FVector::ZeroVector;

	void Update(bool bFirst);
	void Want(int32 Deck, bool bUrgent);
	void Drop(FDeckLevel& D);
	bool CaptainPosition(FVector& OutFeet) const;
	const UAstraShipPlan* Plan() const;
	friend struct FAstraDeckStreamingConsole;
};
