// Copyright ASTRA. UE::Renderer::Private::ITemporalUpscaler implemented with Apple's MetalFX temporal scaler.

#pragma once

#include "CoreMinimal.h"
#include "AstraMetalFXBridge.h"
#include "SceneView.h"
#include "TemporalUpscaler.h"
#include "Templates/RefCounting.h"

class FAstraMetalFXUpscaler final : public UE::Renderer::Private::ITemporalUpscaler
{
public:
	using FContextPtr = TSharedPtr<AstraMetalFX::FScalerContext, ESPMode::ThreadSafe>;

	/**
	 * What the view state keeps between frames for us: the scaler it was accumulating with (whose own history lives inside
	 * MetalFX) and the view matrices of that frame, from which the next frame derives the camera motion.
	 */
	class FHistory final : public IHistory, public TRefCountingMixin<FHistory>
	{
	public:
		FHistory(FContextPtr InContext, const FViewMatrices& InViewMatrices, FIntPoint InOutputSize, uint32 InDeclineEpoch)
			: Context(MoveTemp(InContext))
			, ViewMatrices(InViewMatrices)
			, OutputSize(InOutputSize)
			, DeclineEpoch(InDeclineEpoch)
		{
		}

		virtual const TCHAR* GetDebugName() const override { return GetUpscalerDebugName(); }

		// MetalFX keeps about two output-sized RGBA16F images of history (an estimate, only used by memory reports).
		virtual uint64 GetGPUSizeBytes() const override { return (uint64)OutputSize.X * (uint64)OutputSize.Y * 16u; }

		virtual void AddRef() const override { TRefCountingMixin<FHistory>::AddRef(); }
		virtual FReturnedRefCountValue Release() const override { return TRefCountingMixin<FHistory>::Release(); }
		virtual FReturnedRefCountValue GetRefCount() const override { return TRefCountingMixin<FHistory>::GetRefCount(); }

		const FContextPtr Context;
		const FViewMatrices ViewMatrices;
		const FIntPoint OutputSize;
		const uint32 DeclineEpoch;   // the manager's count of frames the game view went without MetalFX when this was made
	};

	explicit FAstraMetalFXUpscaler(FContextPtr InContext);

	/** The same pointer for every call: the engine compares it with the history's name by address. */
	static const TCHAR* GetUpscalerDebugName();

	//~ ITemporalUpscaler
	virtual const TCHAR* GetDebugName() const override { return GetUpscalerDebugName(); }
	virtual FOutputs AddPasses(FRDGBuilder& GraphBuilder, const FSceneView& View, const FInputs& Inputs) const override;
	virtual float GetMinUpsampleResolutionFraction() const override;
	virtual float GetMaxUpsampleResolutionFraction() const override;
	virtual ITemporalUpscaler* Fork_GameThread(const FSceneViewFamily& ViewFamily) const override;

private:
	FContextPtr Context;
};
