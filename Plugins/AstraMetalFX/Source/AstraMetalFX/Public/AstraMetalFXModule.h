// Copyright ASTRA. The MetalFX temporal upscaler: a Mac-only replacement of TSR for the game view.
//
//   r.AstraMetalFX 0/1         MetalFX (default) or TSR, switchable at run time; TSR also whenever MetalFX cannot run
//   r.AstraMetalFX.Debug 0/1/2 shows the motion vectors (1) or the moving-object pixels (2) instead of the image
//   r.AstraMetalFX.LogInterval seconds between log lines with the GPU cost (0 = never)
//   stat AstraMetalFX          the GPU cost of the MetalFX work (Development builds)
//   astra.metalfx.status       prints what it is doing and why, and the cost

#pragma once

#include "CoreMinimal.h"
#include "Modules/ModuleInterface.h"

DECLARE_LOG_CATEGORY_EXTERN(LogAstraMetalFX, Log, All);

/** A snapshot of what the MetalFX upscaler is doing, for menus, the test harness and the logs. */
struct FAstraMetalFXStatus
{
	bool bSupported = false;    // a Mac on the Metal RHI with a GPU MetalFX supports
	bool bEnabled = false;      // r.AstraMetalFX is on
	bool bActive = false;       // the last frame of the game view was upscaled by MetalFX (otherwise TSR)
	FString Reason;             // why MetalFX is not running, when it is not
	FIntPoint OutputSize = FIntPoint::ZeroValue;
	FString ColorFormat;  // the scene color format the running scaler was built for (R11G11B10F or RGBA16F depending on the quality level)
	float LastGpuMs = 0.0f;     // GPU time of the last MetalFX command buffer: motion kernel, exposure and the scaler
	float AverageGpuMs = 0.0f;
	uint64 FramesUpscaled = 0;
	uint64 FallbackFrames = 0;   // frames that got a bilinear stretch instead of MetalFX (a format change in flight, a failure)
	uint64 Errors = 0;
};

class ASTRAMETALFX_API FAstraMetalFXModule : public IModuleInterface
{
public:
	/** Null when the module is not loaded (any platform but the Mac). */
	static FAstraMetalFXModule* Get();

	virtual void StartupModule() override;
	virtual void ShutdownModule() override;

	FAstraMetalFXStatus GetStatus() const;
};
