// The damage inside the Aquila, headless (DISTRUZIONE's bench; docs/ARCHITETTURA.md §6: a support agent cannot run the game, but it can
// run the ship): hits scripted on the real plan and the real damage model, the air that leaves and stops at the pressure bulkheads, the
// fire that spreads and is put out, the people of VITA hurt where they stood, the damage-control teams that arrive, the Captain in a
// compartment that empties, and the whole Aquila under the strike group's fire. It prints the verdict and writes a record.
//
//   UnrealEditor-Cmd ASTRA.uproject -run=AstraDamageSim [-scenario=trace|air|fire|people|captain|survive|all] [-seed=1] [-seconds=600]
//                    [-set="astra.damage.hole=1.2,astra.damage.fire=0.8"] [-out=Saved/Damage/run.json] -nullrhi -unattended -nosound
//
// tools/damage.py wraps it. The exit code is 0 when every check passes.

#pragma once

#include "CoreMinimal.h"
#include "Commandlets/Commandlet.h"
#include "AstraDamageSimCommandlet.generated.h"

UCLASS()
class UAstraDamageSimCommandlet : public UCommandlet
{
	GENERATED_BODY()

public:
	UAstraDamageSimCommandlet();
	virtual int32 Main(const FString& Params) override;
};
