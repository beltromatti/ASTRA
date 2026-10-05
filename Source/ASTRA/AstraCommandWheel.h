// ASTRA — the Captain's orders without a word: hold G, point, let go (or a number key while it is open).
//
// The user's games of 5 Oct ("sento di non aver il controllo"): every order went through the voice, the recogniser and a model before the ship moved.
// The wheel gives the commonest orders of a fight at once — fire, the target he is looking at, missiles, fighters, shields, alert, the main screen —
// by the very commands the officers' tools use (UAstraShipSubsystem::ApplyCommand, `by: captain`: the consoles show them as the Captain's, in amber),
// and tells the bridge, so that the officer at that station knows it was his order and answers for it. The voice stays the way to say anything else.

#pragma once

#include "CoreMinimal.h"

class APlayerController;
class SAstraCommandWheelWidget;

class FAstraCommandWheel
{
public:
	/** G down: the items as the ship stands now and the target the Captain looks at (through the window, on the main screen, else tactical's, else the
	 *  nearest hostile); the wheel shows and the look holds still. False when there is nothing to command from where he is. */
	bool Open(APlayerController* PC);
	/** The mouse moves the pointer; the item under it is lit. */
	void Tick(APlayerController* PC, float DeltaTime);
	/** G up (or a number key, or Esc): carry out the lit item (bExecute) and close. */
	void Close(APlayerController* PC, bool bExecute);
	void Pick(APlayerController* PC, int32 Index);
	bool IsOpen() const { return bOpen; }

private:
	struct FItem
	{
		FString Label;          // what the button says ("WEAPONS FREE")
		FString Sub;            // the second line: on whom, what stands now
		bool bOn = false;       // what stands now is this
		bool bEnabled = true;
		TFunction<bool(FString& Detail)> Run;
		FString Told;           // what the bridge hears it was ("weapons free on every hostile in range")
	};
	bool bOpen = false;
	TArray<FItem> Items;
	int32 Lit = INDEX_NONE;
	FVector2D Pointer = FVector2D::ZeroVector;
	FString TargetId, TargetLine;
	TSharedPtr<SAstraCommandWheelWidget> Widget;

	void Build(APlayerController* PC);
	void Show(APlayerController* PC);
	void Hide(APlayerController* PC);
	void Execute(APlayerController* PC, int32 Index);
	FString PickTarget(APlayerController* PC, FString& OutLine) const;
};
