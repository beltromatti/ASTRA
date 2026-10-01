// Augmented reality on the bridge's bow window (docs/ARCHITETTURA.md §5): the contacts the Captain can see through the
// glass get a thin bracket and a small label (name, range), like the Falcon's canopy but quieter — a ship at 30 km is a
// speck of light, and the window says what it is. Only through the window (the arc of glass around the bow), never over
// the main viewscreen's image, never indoors elsewhere. The player controller keeps one and updates it every frame.

#pragma once

#include "CoreMinimal.h"

class AAstraHoloTable;
class APlayerController;
class SWidget;

class FAstraWindowHud
{
public:
	/** Show, hide and fill the overlay for this frame (on the bridge only; ops' window AR on). */
	void Tick(APlayerController* PC, float DeltaTime);
	void Remove(APlayerController* PC);

private:
	TSharedPtr<class SAstraWindowHudWidget> Widget;
	TWeakObjectPtr<AAstraHoloTable> HoloTable;   // the names keep off it (its plot names the same ships)
	float Alpha = 0.f;
};
