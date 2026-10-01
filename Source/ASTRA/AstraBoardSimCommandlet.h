// The fight inside the Aquila, headless (ABBORDAGGI's bench; docs/ABBORDAGGI.md): the plan as the soldiers see it (portals, corners, lines of sight,
// routes), duels and squad fights in a corridor (who wins, how fast, with and without cover and the flank), and a whole boarding of the real ship (a
// Mandate boarding party through a breach, the marines of the Aquila on watch and the reaction team: who holds, at what cost, how long). It prints the
// verdict and writes a record.
//
//   UnrealEditor-Cmd ASTRA.uproject -run=AstraBoardSim [-scenario=map|duel|squad|flank|board|rules|all] [-seed=1] [-seeds=20] [-boarders=10]
//                    [-set="MandateSkill=0.8,HoldS=60"] [-out=Saved/Boarding/run.json] -nullrhi -unattended -nosound
//
// tools/boarding.py wraps it. The exit code is 0 when every check passes.

#pragma once

#include "CoreMinimal.h"
#include "Commandlets/Commandlet.h"
#include "AstraBoardSimCommandlet.generated.h"

UCLASS()
class UAstraBoardSimCommandlet : public UCommandlet
{
	GENERATED_BODY()

public:
	UAstraBoardSimCommandlet();
	virtual int32 Main(const FString& Params) override;
};
