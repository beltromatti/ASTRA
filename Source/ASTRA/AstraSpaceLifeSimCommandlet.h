// The living space's bench (docs/SPAZIO.md): a system's traffic run without rendering, as fast as the CPU allows, and a record of what it did — routes flown, berths used, the
// Gate's queue, the reactions to a war, what a tick costs — with checks of the invariants that must always hold (no berth held twice, no vessel in two places, nothing outside the
// system's bounds, nothing faster than its engines).
//
//   UnrealEditor-Cmd ASTRA.uproject -run=AstraSpaceSim -seconds=3600 [-system=Aurelia] [-seed=1] [-step=0.1] [-every=10] [-out=Saved/Space/run.json] [-selftest]
//                    [-at="600=astra.space.alert 25|900=astra.space.alert 0"] [-exec="astra.space.density 2"] -nullrhi -unattended -nosound
//
// -selftest runs the checks every few seconds and ends with SPACE_SELFTEST_OK (exit 0) or the failed checks (exit 1). tools/space.py drives it.

#pragma once

#include "CoreMinimal.h"
#include "Commandlets/Commandlet.h"
#include "AstraSpaceLifeSimCommandlet.generated.h"

UCLASS()
class UAstraSpaceSimCommandlet : public UCommandlet
{
	GENERATED_BODY()

public:
	UAstraSpaceSimCommandlet();
	virtual int32 Main(const FString& Params) override;
};
