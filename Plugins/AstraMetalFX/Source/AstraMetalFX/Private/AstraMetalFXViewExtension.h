// Copyright ASTRA. The scene view extension that, every frame, decides whether the game view is upscaled by MetalFX or by
// the engine's TSR, and installs the upscaler on the view family when it is ours.

#pragma once

#include "CoreMinimal.h"
#include "SceneViewExtension.h"

class FAstraMetalFXViewExtension final : public FSceneViewExtensionBase
{
public:
	explicit FAstraMetalFXViewExtension(const FAutoRegister& AutoRegister);

	//~ ISceneViewExtension
	virtual void SetupViewFamily(FSceneViewFamily& InViewFamily) override {}
	virtual void SetupView(FSceneViewFamily& InViewFamily, FSceneView& InView) override {}
	virtual void BeginRenderViewFamily(FSceneViewFamily& InViewFamily) override;

private:
	/** Only the game's own, single, real-time view is a candidate: scene captures, editor viewports, split screen keep TSR. */
	static bool IsCandidate(const FSceneViewFamily& Family);
};
