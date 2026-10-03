// The playtest harness: lets a test driver (tools/play.py) play the game like a person — real key presses through
// Slate, looking around, speaking or typing to the crew, console commands, screenshots with the UI — and read what
// happened, in order, with times. Off in Shipping builds; on only with -astra_harness (port 8770, -astra_harness_port=N).
//
// FAstraTimeline is always on: a small ring buffer of what the game did (lines spoken, ship events, commands, what the
// Captain said), each with the wall-clock time and the game time. The harness serves it; it also helps debugging.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "Containers/Ticker.h"
#include "AstraHarness.generated.h"

class FJsonObject;
struct FHttpServerRequest;
struct FKey;

struct ASTRA_API FAstraTimeline
{
	/** One thing that happened: Kind is short ("line", "event", "cmd", "captain", "heard", "input", …). */
	static void Record(const TCHAR* Kind, const FString& Text);
	/** Entries after the given wall-clock time (seconds of FPlatformTime), oldest first, as a JSON array text. */
	static FString JsonSince(double RealTime, int32 MaxEntries = 400);
	/** The game world whose clock stamps the entries (set by the harness or by the game). */
	static void SetWorld(UWorld* World);
};

UCLASS()
class UAstraHarness : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

private:
	bool Tick(float DeltaTime);
	UWorld* GameWorld() const;
	APlayerController* PC() const;
	void BindWorld();

	// the requests (each answers JSON)
	TSharedRef<FJsonObject> StateJson() const;
	FString Key(const FString& KeyName, const FString& Action, double Hold);
	FString Look(double YawDeg, double PitchDeg);
	FString Shot(const FString& Path, bool bShowUI);
	static void SendKey(const FKey& Key, bool bDown);

	FTSTicker::FDelegateHandle TickHandle;
	TWeakObjectPtr<UWorld> BoundWorld;
	FDelegateHandle ShipEventHandle;
	struct FPendingRelease { FString Key; double At; };
	TArray<FPendingRelease> Releases;
	double HoverUntil = 0.0;              // /teleport: the Captain floats where he was put until a floor is under him (a deck still streaming in)
	double FpsAvg = 0.0;
	int32 Port = 8770;
	bool bStarted = false;
};
