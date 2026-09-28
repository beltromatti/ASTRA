// Copyright Epic Games, Inc. All Rights Reserved.


#include "ASTRACameraManager.h"
#include "AstraBattleSubsystem.h"
#include "Engine/World.h"

AASTRACameraManager::AASTRACameraManager()
{
	// set the min/max pitch
	ViewPitchMin = -70.0f;
	ViewPitchMax = 80.0f;
}

void AASTRACameraManager::UpdateViewTarget(FTViewTarget& OutVT, float DeltaTime)
{
	Super::UpdateViewTarget(OutVT, DeltaTime);
	UAstraBattleSubsystem* Battle = GetWorld() ? GetWorld()->GetSubsystem<UAstraBattleSubsystem>() : nullptr;
	const float A = Battle ? Battle->ConsumeShake(DeltaTime) : 0.f;
	if (A > 0.001f)
	{
		ShakeTime += DeltaTime;
		const float T = ShakeTime;
		const float Amp = A * A;
		OutVT.POV.Location += FVector(FMath::Sin(T * 37.f), FMath::Sin(T * 29.f + 1.3f), FMath::Sin(T * 43.f + 2.1f)) * 2.2f * Amp;
		OutVT.POV.Rotation += FRotator(FMath::Sin(T * 31.f) * 0.9f, FMath::Sin(T * 23.f + 0.7f) * 0.7f, FMath::Sin(T * 17.f) * 0.6f) * Amp;
	}
}
