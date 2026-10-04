// The self-test of how the game starts the mind (AstraMindLaunch.h, docs/WINDOWS.md): no Windows PC is needed to check what the game does on one.
//
//   1. the logic of every system, against made-up machines (Mac checkout, Mac app, Windows package, Windows checkout, Linux, uv in each of its places,
//      uv missing, the overrides, the door's port): which mind, which uv, which data folder, which environment, in the form each system wants;
//   2. this machine's own plan;
//   3. -probe: the real launch of a program that writes the environment it was given (and a check that the game's own environment is as it was);
//   4. -launch=dev|packaged: the real mind, started by the same function the game calls (the repository's, or a copy laid out like a package with its own
//      data folder and Python environment), on a port of its own with no models, reached by a WebSocket client like the game's, then stopped.
//
//   UnrealEditor-Cmd ASTRA.uproject -run=AstraMindLaunch [-probe] [-launch=dev|packaged] -nullrhi -unattended -nosound -nopause
//
// The exit code is the number of checks that failed.

#pragma once

#include "CoreMinimal.h"
#include "Commandlets/Commandlet.h"
#include "AstraMindLaunchCommandlet.generated.h"

UCLASS()
class UAstraMindLaunchCommandlet : public UCommandlet
{
	GENERATED_BODY()

public:
	UAstraMindLaunchCommandlet();
	virtual int32 Main(const FString& Params) override;
};
