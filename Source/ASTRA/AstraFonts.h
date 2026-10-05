// ASTRA — the game's two UI fonts, for every Slate widget and canvas that writes with them.

#pragma once

#include "CoreMinimal.h"
#include "Engine/Font.h"
#include "UObject/UObjectGlobals.h"

namespace AstraFonts
{
	/** A font loaded once and kept for the life of the process. A Slate widget's FSlateFontInfo holds a bare pointer to its font: one the
	 *  garbage collector freed under a widget crashed the app as it painted (5 Oct, twice in the Captain's games: the names over the window). */
	inline UFont* Keep(const TCHAR* Path)
	{
		UFont* F = LoadObject<UFont>(nullptr, Path);
		if (F && !F->IsRooted())
		{
			F->AddToRoot();
		}
		return F;
	}
	inline UFont* Mono() { return Keep(TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Mono.F_ASTRA_Mono")); }
	inline UFont* Title() { return Keep(TEXT("/Game/ASTRA/UI/Fonts/F_ASTRA_Title.F_ASTRA_Title")); }
}
