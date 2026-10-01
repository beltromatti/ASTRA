// Copyright ASTRA.

#include "AstraMetalFXViewExtension.h"
#include "AstraMetalFXManager.h"
#include "AstraMetalFXUpscaler.h"
#include "SceneUtils.h"
#include "SceneView.h"

FAstraMetalFXViewExtension::FAstraMetalFXViewExtension(const FAutoRegister& AutoRegister)
	: FSceneViewExtensionBase(AutoRegister)
{
}

const TCHAR* FAstraMetalFXViewExtension::GetRejection(const FSceneViewFamily& Family, bool& bOutMainGameView)
{
	bOutMainGameView = false;
	const FSceneView* View = Family.Views.Num() > 0 ? Family.Views[0] : nullptr;
	if (!View || !View->bIsGameView || View->bIsSceneCapture || View->bIsReflectionCapture || View->bIsPlanarReflection)
	{
		return TEXT("not the game's main view");
	}
	bOutMainGameView = true;

	if (Family.Views.Num() != 1)
	{
		return TEXT("the view family has several views (split screen)");
	}
	if (!Family.bRealtimeUpdate)
	{
		return TEXT("the view family is not real-time");
	}
	if (Family.GetTemporalUpscalerInterface() != nullptr)
	{
		return TEXT("another upscaler is already installed on the view family");
	}
	if (Family.GetFeatureLevel() < ERHIFeatureLevel::SM5)
	{
		return TEXT("the feature level is below SM5");
	}
	if (!Family.EngineShowFlags.TemporalAA || !Family.EngineShowFlags.PostProcessing)
	{
		return TEXT("the TemporalAA or PostProcessing show flag is off");
	}
	// The view must be one TSR (or TAA) would accumulate: a temporal method, with a view state to keep the history in.
	if (!IsTemporalAccumulationBasedMethod(View->AntiAliasingMethod))
	{
		return TEXT("the anti-aliasing method is not temporal (r.AntiAliasingMethod 4 is TSR)");
	}
	if (View->State == nullptr)
	{
		return TEXT("the view has no view state to keep a history in");
	}
	return nullptr;
}

void FAstraMetalFXViewExtension::BeginRenderViewFamily(FSceneViewFamily& InViewFamily)
{
	FAstraMetalFXManager& Manager = FAstraMetalFXManager::Get();

	bool bMainGameView = false;
	if (const TCHAR* Rejection = GetRejection(InViewFamily, bMainGameView))
	{
		if (bMainGameView)
		{
			Manager.NoteDeclinedFrame(Rejection);   // the game view itself, but not upscaled by us: its MetalFX history goes stale
		}
		return;   // anything else is not ours: the engine's own upscaler, untouched
	}

	if (!Manager.IsEnabledByCVar())
	{
		Manager.NoteDeclinedFrame(TEXT("r.AstraMetalFX is 0"));
		return;
	}
	if (!Manager.IsAvailable())
	{
		Manager.NoteDeclinedFrame(TEXT("MetalFX is not available on this machine or failed earlier in this session"));
		return;
	}
	if (!Manager.IsEngineUpscalerSwitchOn())
	{
		Manager.NoteDeclinedFrame(TEXT("r.TemporalAA.Upscaler is 0 (the engine ignores third-party upscalers)"));
		return;
	}

	// MetalFX writes at the size the engine will ask for: the secondary view rectangle (the game view, before the final
	// screen-percentage upscale to the window). Same formula as FViewInfo::GetSecondaryViewRectSize in the renderer.
	const FSceneView& View = *InViewFamily.Views[0];
	const FIntPoint OutputSize(
		FMath::CeilToInt(View.UnscaledViewRect.Width() * InViewFamily.SecondaryViewFraction * View.SceneViewInitOptions.OverscanResolutionFraction),
		FMath::CeilToInt(View.UnscaledViewRect.Height() * InViewFamily.SecondaryViewFraction * View.SceneViewInitOptions.OverscanResolutionFraction));
	const FAstraMetalFXManager::FContextPtr Context = Manager.AcquireContext(OutputSize);
	if (!Context.IsValid())
	{
		Manager.NoteDeclinedFrame(TEXT("the scaler for this window size is being built"));   // or it failed: TSR this frame
		return;
	}

	InViewFamily.SetTemporalUpscalerInterface(new FAstraMetalFXUpscaler(Context, Manager.GetDeclineEpoch()));
	Manager.NoteUpscaledFrame(OutputSize);
}
