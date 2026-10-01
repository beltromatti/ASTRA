// ASTRA — the ship's lifts (docs/ASCENSORI.md). Real turbolifts and the Spine shuttle: a car that really moves in its shaft (or along its line) and carries
// whoever is aboard, doors that open together and never close on someone, a dispatch that answers calls from the landings and from inside, a list of decks and
// places on the car's own screen, the Captain's voice (a tool of the crew's mind), and the crew who use them as the Captain does.
//
// This subsystem reads the plan's `vertical[]` and `transit[]` (version 2: docs/brief/NAVE-3.md), builds the shafts, cars and landings in the persistent level
// (a line a frame, nearest the Captain first), and is what the controller (E), the minds (`lift_go`) and the life simulation (the crew's bodies) talk to.
// The cars run themselves (AAstraLiftCar ticks its brain, only while something moves): at rest the whole network costs a counter a frame.

#pragma once

#include "CoreMinimal.h"
#include "Async/Future.h"
#include "Dom/JsonObject.h"
#include "Subsystems/WorldSubsystem.h"
#include "AstraLiftBrain.h"
#include "AstraLiftData.h"
#include "AstraLiftSubsystem.generated.h"

class AAstraLiftCar;
class AAstraLiftLanding;
class AAstraLiftShaft;
class UCanvas;
class UCanvasRenderTarget2D;
class UFont;
class UAstraLiftSubsystem;

/** A car's screen: a canvas render target painted from the lift's state (the deck list, the deck the car is at, where it goes). */
UCLASS()
class UAstraLiftScreen : public UObject
{
	GENERATED_BODY()

public:
	TWeakObjectPtr<UAstraLiftSubsystem> Owner;
	int32 Line = INDEX_NONE;
	UPROPERTY() TObjectPtr<UCanvasRenderTarget2D> Target;
	double LastPaint = -1.0e9;

	UFUNCTION()
	void Draw(UCanvas* Canvas, int32 Width, int32 Height);
};

USTRUCT()
struct FAstraLiftRuntime
{
	GENERATED_BODY()

	UPROPERTY() TObjectPtr<AAstraLiftCar> Car;
	UPROPERTY() TObjectPtr<AAstraLiftShaft> Shaft;
	UPROPERTY() TArray<TObjectPtr<AAstraLiftLanding>> Landings;
	UPROPERTY() TObjectPtr<UAstraLiftScreen> Screen;
};

UCLASS()
class ASTRA_API UAstraLiftSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	virtual void Deinitialize() override;
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UAstraLiftSubsystem, STATGROUP_Tickables); }

	// ------------------------------------------------------------------------------------------------------------------------------ building
	/** Reads a plan (or the test plan) now, on this thread. The game does it on a worker, from OnWorldBeginPlay. */
	bool LoadNetwork(const FString& PlanFile);
	/** Takes a network that was read elsewhere. */
	void SetNetwork(FAstraLiftNetwork&& InNet);
	/** Builds every shaft, car and landing at once (the bench; the game does a line a frame). */
	void BuildNow();
	/** Takes every shaft, car and landing out of the world again (the bench builds several networks in one world). */
	void Reset();
	bool IsBuilt() const { return bBuilt; }
	bool IsLoading() const { return State == EState::Loading; }
	const FAstraLiftNetwork& Network() const { return Net; }
	int32 NumLines() const { return Net.Lines.Num(); }
	AAstraLiftCar* CarOf(int32 Line) const { return Run.IsValidIndex(Line) ? Run[Line].Car.Get() : nullptr; }
	AAstraLiftLanding* LandingOf(int32 Line, int32 Stop) const { return Run.IsValidIndex(Line) && Run[Line].Landings.IsValidIndex(Stop) ? Run[Line].Landings[Stop].Get() : nullptr; }
	UAstraLiftScreen* ScreenOf(int32 Line) const { return Run.IsValidIndex(Line) ? Run[Line].Screen.Get() : nullptr; }

	// ---------------------------------------------------------------------------------------------------------------------- the Captain's use
	/** E: inside a car it opens the deck list on the car's screen, and chooses the one that is marked when it is open; at a landing it calls the car. True when
	 *  the key was a lift's. OutNotice: what to say in a line on the screen. */
	bool Use(APawn* Pawn, FString& OutNotice);
	/** The car the Captain is in (by line), INDEX_NONE when he is in none. */
	int32 PlayerLine() const { return InLine; }
	/** The car's list: W/S and the mouse move the mark, E or a click chooses, Esc closes it. */
	bool IsMenuOpen() const { return MenuLine != INDEX_NONE; }
	void MenuMove(int32 Delta);
	bool MenuChoose(FString& OutNotice);
	void MenuClose();
	/** The mouse: where the Captain's view points. The row under it is marked (when it changes). Returns the row, or INDEX_NONE. */
	int32 MenuPoint(const FVector& EyeCm, const FVector& Dir);
	/** A deck by its number, from the open list or from the voice: the car the Captain is in goes there. */
	bool GoToDeck(int32 Deck, FString& Detail);
	/** The Captain is in a car and asks it for a stop (the voice): `destination` is the stop's id ("d7", "sec_h"), else `deck`, else `place`. */
	bool GoByVoice(const TSharedPtr<FJsonObject>& Args, FString& Detail);
	/** What the mind needs when the Captain speaks inside a car: the car, where it is and goes, the stops with their decks and notable places. Null outside one. */
	TSharedPtr<FJsonObject> ContextJson() const;
	/** The call from a landing (a lamp, a car on its way): true when a car was called. */
	bool CallAt(int32 Line, int32 Stop, FString& OutNotice);
	/** A landing's panel within reach of a place on the floor (for the controller's rule that the lift is what E means here). */
	bool IsNearPanel(const FVector& Feet) const;

	// --------------------------------------------------------------------------------------------------------------------------- for the screen
	struct FRow { int32 Stop = INDEX_NONE; FString Label, Name, Places; bool bHere = false; };
	/** The rows of a car's list, top to bottom: a vertical lift from its highest deck down, the shuttle from its first stop to its last. */
	void MenuRows(int32 Line, TArray<FRow>& Out) const;
	int32 MenuSelected() const { return MenuSel; }
	/** What the screen says besides the list: "DECK 4", "▼ DECK 7" while it moves, "DECK 7 · ARRIVING" while it waits for the deck. */
	FString StatusLine(int32 Line, FLinearColor& OutColor) const;
	/** The deck number of the screen's big figure, and the stop it is going to (INDEX_NONE at rest). */
	int32 ShownStop(int32 Line) const;

	// ---------------------------------------------------------------------------------------------------------------------------------- hooks
	FAstraLiftBrain::FHooks MakeHooks(int32 Line);
	void OnCarEvent(int32 Line, const FAstraLiftEvent& E);
	bool DoorwayBusy(int32 Line, int32 Stop) const;
	bool DeckReady(int32 Line, int32 Stop) const;
	void WantDeck(int32 Line, int32 Stop) const;
	void ForceDeck(int32 Line, int32 Stop) const;

	// ------------------------------------------------------------------------------------------------------------------------------- the crew
	/** A route's two ends are the ends of a lift ride (VITA walks that part in the car). */
	bool FindRide(const FVector& A, const FVector& B, int32& OutLine, int32& OutFrom, int32& OutTo) const { return Net.FindRide(A, B, OutLine, OutFrom, OutTo); }
	/** The seconds a crew member (no body, far from the Captain) spends on a ride between two places: what VITA's abstract clock should use. */
	float AverageRideSeconds() const;
	float RideSeconds(int32 Line, int32 From, int32 To) const;
	/** The crew's bodies: a person at a landing presses the call (Dir by where they are going), boards the car that stands there with its doors open and
	 *  heading their way, takes a place in it, chooses their stop, and gets out where the doors open at it. */
	void RiderCall(int32 Line, int32 From, int32 To);
	bool CanBoard(int32 Line, int32 From, int32 To) const;
	int32 TakeSlot(int32 Line, int32 Who);
	void FreeSlot(int32 Line, int32 Slot);
	void RiderChoose(int32 Line, int32 To);
	bool CanAlight(int32 Line, int32 To) const;
	/** Whether the Captain is in the car (his place counts as taken: a body does not stand through him). */

	// ------------------------------------------------------------------------------------------------------------------------------- the bench
	/** The bench's world: no pawn, no listener, no streaming. Overrides stand in for them. */
	struct FTestHooks
	{
		TFunction<bool(const FVector& Cm)> DeckReadyAt;         // a deck is in the world (the point: the lobby)
		TFunction<void(const FVector& Cm)> ForceReadyAt;
		TFunction<void(const FVector& Cm)> WantReadyAt;
		TFunction<bool(const FVector& Cm)> Occupied;           // somebody is in the doorway at this point
		TFunction<bool()> CaptainInterested;                    // the Captain waits for the deck (so the doors hold for it)
	};
	FTestHooks Test;
	bool bBench = false;                 // sounds and lights off
	double TickMicros() const { return LastTickUs; }
	int64 TickCount() const { return Ticks; }
	FString Describe() const;
	/** The Captain's pawn (the bench puts its own). */
	void SetCaptain(APawn* P) { CaptainPawn = P; }
	APawn* Captain() const;

private:
	enum class EState : uint8 { Idle, Loading, Ready, Failed };
	EState State = EState::Idle;
	FAstraLiftNetwork Net;
	TFuture<TSharedPtr<FAstraLiftNetwork>> NetFuture;
	UPROPERTY() TArray<FAstraLiftRuntime> Run;
	bool bBuilt = false;
	int32 NextToBuild = 0;
	TArray<int32> BuildOrder;

	// the Captain
	TWeakObjectPtr<APawn> CaptainPawn;
	int32 InLine = INDEX_NONE;              // the car he is in
	int32 NearLine = INDEX_NONE;            // a landing he waits at: its line and stop
	int32 NearStop = INDEX_NONE;
	int32 MenuLine = INDEX_NONE;
	int32 MenuSel = 0;
	int32 HoverRow = INDEX_NONE;
	double MenuOpenedAt = 0.0;
	float SlowT = 0.f;
	double LastTickUs = 0.0;
	int64 Ticks = 0;
	TArray<TArray<int32>> SlotOwner;        // per line: who stands at each place of the car

	UPROPERTY() TObjectPtr<UFont> TitleFont;
	UPROPERTY() TObjectPtr<UFont> MonoFont;

	void BuildLine(int32 Line);
	void Slow(float Dt);
	void UpdateCaptain();
	void EnsureScreen(int32 Line);
	/** The car's screen painted again: at once, or when it is due (the Captain is in it: ten times a second while it moves, twice at rest). */
	void RepaintScreen(int32 Line, bool bNow);
	void PaintScreen(int32 Line, UCanvas* Canvas, int32 W, int32 H);
	int32 DisplayToStop(int32 Line, int32 Row) const;
	int32 StopToRow(int32 Line, int32 Stop) const;
	bool StartRide(int32 Line, int32 Stop, FString& Detail);
	bool InterestedIn(int32 Line) const;
	FString StopName(int32 Line, int32 Stop) const;
	friend class UAstraLiftScreen;
	friend struct FAstraLiftConsole;
};
