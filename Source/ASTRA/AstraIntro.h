// ASTRA — the introduction: a short tour that opens a player's first campaign (and can be watched again from the title menu). A camera moves
// through the real ship and her war: the Aquila from outside, an allied ship, the bridge and its stations, the main screen, the holo table, the
// Captain's chair, a corridor, the flight deck, the Janus Gate; a narrator says, in the player's language, who they are, where, what they can do
// and how. Subtitled; Space (Enter, a click) goes to the next shot and Esc skips it all. It plays before the war begins: nothing happens unseen.
#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "AstraIntro.generated.h"

class ACameraActor;
class SWidget;
class STextBlock;
class SBorder;

UCLASS()
class ASTRA_API UAstraIntroSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual void Deinitialize() override;
	virtual void Tick(float DeltaTime) override;
	virtual bool IsTickable() const override { return bPlaying; }
	virtual bool IsTickableWhenPaused() const override { return true; }
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UAstraIntroSubsystem, STATGROUP_Tickables); }

	/** Play the tour; Done runs when it ends, played through or skipped. */
	void Play(TFunction<void()> Done);
	bool IsPlaying() const { return bPlaying; }
	/** Esc: the whole tour. */
	void Skip();
	/** Space: the next shot (the narrator stops). */
	void Next();
	/** Has this player seen it, through or skipped (GameUserSettings.ini)? */
	static bool Seen();
	/** Testing and pictures: the tour's shot N (from 1), silent and held where its camera ends (`astra.intro.shot N`; Esc or
	 *  `astra.intro.skip` ends it). */
	void HoldShot(int32 N);

private:
	struct FShot
	{
		FVector From, To;            // the camera (world cm)
		FVector LookFrom, LookTo;    // where it looks
		float Fov = 60.f;
		int32 Line = 0;              // the narrator's line (AstraIntro.cpp: the script)
		int32 Deck = -1;             // a deck that must be loaded before the shot (the flight deck)
	};
	TArray<FShot> Shots;
	int32 Index = -1;
	float T = 0.f;                   // since the shot began
	float Black = 1.f;               // the dip between shots: 1 black, 0 clear
	float BlackWant = 1.f;
	float WaitDeck = 0.f;            // the next shot's deck is loading: seconds waited in the dark
	float Silent = 0.f;              // the narrator has been silent this long since he spoke
	float FinishT = 0.f;
	bool bPlaying = false;
	bool bNarrated = false;          // the shot's line went to the mind
	bool bVoiceHeard = false;        // ... and the narrator began to say it
	bool bLeaving = false;           // the shot is over: fading to the next
	bool bNextWanted = false;        // Space (taken by the next tick)
	bool bSkipWanted = false;        // Esc
	bool bFinishing = false;         // the end: back to the Captain's own eyes
	bool bBlendHome = false;         // ... by a blend from the last shot (played through), else by a cut in the dark (skipped)
	bool bReturned = false;          // ... and the view is back with them
	bool bHold = false;              // HoldShot: no narrator, no end
	TFunction<void()> OnDone;
	UPROPERTY() TObjectPtr<ACameraActor> Camera;
	TSharedPtr<SWidget> Widget;
	TSharedPtr<SWidget> Content;     // (the viewport's SWeakWidget holds it weakly: kept here)
	TSharedPtr<STextBlock> Caption;
	TSharedPtr<SBorder> Shade;
	TSharedPtr<class SVerticalBox> Bars;
	TSharedPtr<class IInputProcessor> Keys;
	class UAstraMindSubsystem* GetMind() const;
	void Build();
	void Begin(int32 I);
	void Finish(bool bBlend);
	void Teardown(bool bWorldGoing);
	float ReadSeconds(int32 Line) const;
	FString LineText(int32 Line) const;
};
