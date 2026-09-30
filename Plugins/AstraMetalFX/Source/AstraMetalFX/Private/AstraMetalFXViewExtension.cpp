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

bool FAstraMetalFXViewExtension::IsCandidate(const FSceneViewFamily& Family)
{
	if (Family.Views.Num() != 1 || !Family.bRealtimeUpdate || Family.GetTemporalUpscalerInterface() != nullptr)
	{
		return false;
	}
	if (Family.GetFeatureLevel() < ERHIFeatureLevel::SM5 || !Family.EngineShowFlags.TemporalAA || !Family.EngineShowFlags.PostProcessing)
	{
		return false;
	}

	const FSceneView* View = Family.Views[0];
	if (!View || !View->bIsGameView || View->bIsSceneCapture || View->bIsReflectionCapture || View->bIsPlanarReflection)
	{
		return false;
	}
	// The view must be one TSR (or TAA) would accumulate: a temporal method, with a view state to keep the history in.
	return IsTemporalAccumulationBasedMethod(View->AntiAliasingMethod) && View->State != nullptr;
}

void FAstraMetalFXViewExtension::BeginRenderViewFamily(FSceneViewFamily& InViewFamily)
{
	if (!IsCandidate(InViewFamily))
	{
		return;   // not ours: the engine's own upscaler, untouched
	}

	FAstraMetalFXManager& Manager = FAstraMetalFXManager::Get();
	if (!Manager.IsEnabledByCVar() || !Manager.IsAvailable())
	{
		Manager.NoteDeclinedFrame();
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
		Manager.NoteDeclinedFrame();   // still being built, or failed: TSR this frame
		return;
	}

	InViewFamily.SetTemporalUpscalerInterface(new FAstraMetalFXUpscaler(Context));
}
