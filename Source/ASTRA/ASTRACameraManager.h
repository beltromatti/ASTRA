// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "Camera/PlayerCameraManager.h"
#include "ASTRACameraManager.generated.h"

/**
 *  Basic First Person camera manager.
 *  Limits min/max look pitch.
 */
UCLASS()
class AASTRACameraManager : public APlayerCameraManager
{
	GENERATED_BODY()
	
public:

	/** Constructor */
	AASTRACameraManager();

protected:
	/** Hull hits shake the view (the ship lurches); amplitude comes from the battle simulation. */
	virtual void UpdateViewTarget(FTViewTarget& OutVT, float DeltaTime) override;

private:
	float ShakeTime = 0.f;
};
