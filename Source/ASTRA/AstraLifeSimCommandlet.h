// A day of life aboard, headless (VITA's bench; docs/ARCHITETTURA.md §6: a support agent cannot run the game, but it can run the ship):
// the ship's 560 people on the real plan, a day of ship time (watches, meals, sleep), an alarm, incidents with damage-control parties,
// wounded taken to the Medbay and healed, and the invariants a living ship must keep. It prints the verdict and writes a record.
//
//   UnrealEditor-Cmd ASTRA.uproject -run=AstraLifeSim [-hours=24] [-hour=0] [-seed=1] [-step=0.25] [-scenario=day|quiet]
//                    [-out=Saved/Life/run.json] -nullrhi -unattended -nosound
//
// tools/life.py run wraps it. The exit code is 0 when every check passes.

#pragma once

#include "CoreMinimal.h"
#include "Commandlets/Commandlet.h"
#include "AstraLifeSimCommandlet.generated.h"

UCLASS()
class UAstraLifeSimCommandlet : public UCommandlet
{
	GENERATED_BODY()

public:
	UAstraLifeSimCommandlet();
	virtual int32 Main(const FString& Params) override;
};
