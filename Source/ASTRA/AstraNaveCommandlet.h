// NAVE-2's bench, headless (a support agent cannot run the game, but it can run the ship's plan): what the lamp pool and the deck streaming read from
// data/ship/aquila_plan.json, and what they do with it. Every lamp is inside its compartment; a Captain who walks the length of every built deck sees
// his lamps light and leave without flicker, a few at a time; the room behind a closed door stays dark until he is at the door; the decks wanted around a
// Captain on a stair column, in a hall and in the keel are the right ones. It prints the verdict; the exit code is 0 when every check passes.
//
//   UnrealEditor-Cmd ASTRA.uproject -run=AstraNave [-step=200] [-max=10] -nullrhi -unattended -nosound

#pragma once

#include "CoreMinimal.h"
#include "Commandlets/Commandlet.h"
#include "AstraNaveCommandlet.generated.h"

UCLASS()
class UAstraNaveCommandlet : public UCommandlet
{
	GENERATED_BODY()

public:
	UAstraNaveCommandlet();
	virtual int32 Main(const FString& Params) override;
};
