// TELETRASPORTO's bench, headless (a support agent cannot run the game, but it can run the world's rules): the lattice transport's rules on scripted cases, each
// one a made-up world and a request with an expected verdict (the shields' faces at both ends, range, jamming along the line, the ship's motion, a Gate's field,
// the room's power and hazards, the lock's life, the arrival's rolls), then the whole subsystem in a headless world on the real plan. It prints each check and the
// verdict; the exit code is 0 when every check passes.
//
//   UnrealEditor-Cmd ASTRA.uproject -run=AstraTransport [-scenario=all|rules|world] [-seed=1] [-out=Saved/Transport/run.json] -nullrhi -unattended -nosound -nopause

#pragma once

#include "CoreMinimal.h"
#include "Commandlets/Commandlet.h"
#include "AstraTransportCommandlet.generated.h"

UCLASS()
class UAstraTransportCommandlet : public UCommandlet
{
	GENERATED_BODY()

public:
	UAstraTransportCommandlet();
	virtual int32 Main(const FString& Params) override;
};
