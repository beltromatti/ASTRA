// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"

/** The version a player sees (the title menu) and the release carries (tools/release_mac.sh, the GitHub release). */
#define ASTRA_VERSION TEXT("0.1.0-alpha")

/** Main log category used across the project */
DECLARE_LOG_CATEGORY_EXTERN(LogASTRA, Log, All);

/** The war bench (AstraWarSimCommandlet) wants the same battle from the same seed: every random stream seeds from
 *  FMath::Rand() instead of the clock while this is on. */
extern ASTRA_API bool GAstraDeterministic;

/** `stat Astra`: where the game thread's time goes among ASTRA's own systems. */
DECLARE_STATS_GROUP(TEXT("ASTRA"), STATGROUP_Astra, STATCAT_Advanced);
