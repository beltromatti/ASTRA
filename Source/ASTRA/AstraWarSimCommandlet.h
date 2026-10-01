// Headless battles for tests and tuning (the war module's bench; docs/ARCHITETTURA.md §6: a support agent cannot run the
// game, but it can run the war): the battle without rendering, as fast as the CPU allows, and a record of what happened.
//
//   UnrealEditor-Cmd ASTRA.uproject -run=AstraWarSim -seconds=900 [-jump=170] [-step=0.1] [-every=5]
//                    [-exec="astra.battle.spawn styx 12 30;astra.cmd station {...}"] [-out=Saved/War/run.json]
//                    -nullrhi -unattended -nosound
//
//   With -mind=<dir> [-mind_dt=1] [-mind_speed=1] the minds are in the loop: every mind_dt battle seconds the battle writes the views
//   the game gives them (s_<k>.json) and waits for the commands they gave (r_<k>.json); see mind/bench/war_arena.py and docs/GUERRA.md §8.
//
// The record: every event and report with its battle time, the truth about every ship every few seconds (positions in km
// from the Aquila, hull and shields, AI mode, target, stance), the stations' modes, and a summary (who died when).

#pragma once

#include "CoreMinimal.h"
#include "Commandlets/Commandlet.h"
#include "AstraWarSimCommandlet.generated.h"

UCLASS()
class UAstraWarSimCommandlet : public UCommandlet
{
	GENERATED_BODY()

public:
	UAstraWarSimCommandlet();
	virtual int32 Main(const FString& Params) override;
};
