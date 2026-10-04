// ASTRA — the little things the drawing of the living space shares (AstraSpaceLifeDraw.cpp: the places, the traffic; AstraSpaceLifeWrecks.cpp: what the war leaves).

#pragma once

#include "CoreMinimal.h"
#include "AstraWarFX.h"

namespace AstraSpaceDraw
{
	/** Where an instance goes when it is not shown (an instance cannot be removed from a page without moving the others': it is made too small to see). */
	inline const FTransform& SpHiddenXf()
	{
		static const FTransform X(FQuat::Identity, FVector::ZeroVector, FVector(0.0001));
		return X;
	}

	inline uint32 SpMix(uint32 A)
	{
		A ^= A >> 16; A *= 0x7FEB352Du; A ^= A >> 15; A *= 0x846CA68Bu; A ^= A >> 16;
		return A;
	}

	/** How much of a lamp shows at this distance (km): all of it near, a little less far, none at the edge of the system. */
	inline float SpLampFade(double Km)
	{
		return 1.f - 0.7f * AstraFx::Ease((float)((Km - 60.0) / 190.0)) - 0.3f * AstraFx::Ease((float)((Km - 215.0) / 35.0));
	}
}
