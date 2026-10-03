// TELETRASPORTO's world bench (AstraTransportBench.cpp): the whole transporter subsystem in a headless world, called by the commandlet's `world` scenario.

#pragma once

#include "CoreMinimal.h"

/** One check of the bench: the commandlet keeps the list and prints the verdict (AstraTransportCommandlet.cpp). */
void AstraXportBenchCheck(const TCHAR* Name, bool bPass, const FString& Detail);

/** The orders, the cycle, the people, the battle's shields, the away team and the damaged room in a world made of the real plan, VITA, the damage model and the battle. Fixtures: where the
 *  cards the Chief would read are written (the mind's tests use them). */
void AstraXportRunWorldBench(const FString& Fixtures);
