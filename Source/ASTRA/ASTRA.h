// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"

/** Main log category used across the project */
DECLARE_LOG_CATEGORY_EXTERN(LogASTRA, Log, All);

/** The war bench (AstraWarSimCommandlet) wants the same battle from the same seed: every random stream seeds from
 *  FMath::Rand() instead of the clock while this is on. */
extern ASTRA_API bool GAstraDeterministic;
