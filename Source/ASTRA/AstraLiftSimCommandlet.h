// ASCENSORI's bench, headless (a support agent cannot run the game, but it can run the lifts): the motion of a car, the dispatch of its calls, a rush hour of
// riders, a character riding a car from Deck 1 to Deck 9 in a real world that ticks (floor, walls, doors, CharacterMovement with the car for its base), the
// doors that never close on someone, the wait for a deck that is not there yet, the Captain's voice, the cost per frame. It prints the verdict; the exit code is
// 0 when every check passes.
//
//   UnrealEditor-Cmd ASTRA.uproject -run=AstraLiftSim [-scenario=all|motion|brain|rush|ride|doors|stream|voice|shuttle|perf] [-plan=<test plan>] [-seed=N] [-riders=N]
//                                                     -nullrhi -unattended -nosound
//   tools/lift.py run                  (the same, with the log kept in Saved/Logs/lift_sim.log)

#pragma once

#include "CoreMinimal.h"
#include "Commandlets/Commandlet.h"
#include "AstraLiftSimCommandlet.generated.h"

UCLASS()
class UAstraLiftSimCommandlet : public UCommandlet
{
	GENERATED_BODY()

public:
	UAstraLiftSimCommandlet();
	virtual int32 Main(const FString& Params) override;
};
