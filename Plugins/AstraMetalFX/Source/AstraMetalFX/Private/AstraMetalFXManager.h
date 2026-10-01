// Copyright ASTRA. The plugin's state: cvars, the scaler contexts (one per output size and scene color format, built on a
// worker thread, swapped in when ready), the fallback latch, the cost counters. One instance, owned by the module, used by
// the view extension (game thread) and the upscaler (render thread).

#pragma once

#include "CoreMinimal.h"
#include "AstraMetalFXBridge.h"
#include "AstraMetalFXModule.h"
#include "HAL/CriticalSection.h"
#include "Stats/Stats.h"
#include <atomic>

DECLARE_STATS_GROUP(TEXT("AstraMetalFX"), STATGROUP_AstraMetalFX, STATCAT_Advanced);
DECLARE_FLOAT_ACCUMULATOR_STAT_EXTERN(TEXT("MetalFX GPU ms (last frame)"), STAT_AstraMetalFXGpuLast, STATGROUP_AstraMetalFX, );
DECLARE_FLOAT_ACCUMULATOR_STAT_EXTERN(TEXT("MetalFX GPU ms (average)"), STAT_AstraMetalFXGpuAverage, STATGROUP_AstraMetalFX, );
DECLARE_DWORD_ACCUMULATOR_STAT_EXTERN(TEXT("MetalFX frames upscaled"), STAT_AstraMetalFXFrames, STATGROUP_AstraMetalFX, );

class FAstraMetalFXViewExtension;

class FAstraMetalFXManager
{
public:
	using FContextPtr = TSharedPtr<AstraMetalFX::FScalerContext, ESPMode::ThreadSafe>;

	static FAstraMetalFXManager& Get();

	/** Module startup (the engine and the RHI are up): checks the machine, registers the view extension, warms the scaler up. */
	void Startup();
	void Shutdown();

	/** r.AstraMetalFX. Game thread. */
	bool IsEnabledByCVar() const;

	/**
	 * False when the engine's own r.TemporalAA.Upscaler is 0: the renderer then ignores third-party upscalers and runs TSR even if
	 * one is installed, so MetalFX must count that frame as declined (its history goes stale). Game thread.
	 */
	bool IsEngineUpscalerSwitchOn() const;

	/** True while MetalFX can run here: supported machine and no failure so far this session. */
	bool IsAvailable() const { return bSupported && !bDisabled.load(); }

	/** A failure: from now on the game view uses TSR, and the reason is logged once. Any thread. */
	void DisableForSession(const FString& Reason);

	/**
	 * Game thread, when a game view wants MetalFX: the scaler for this output size and for the scene color format the engine
	 * hands to upscalers (guessed from the engine's own setting at start, then what the render thread saw last) if it is ready,
	 * else null (TSR this frame) and a worker thread builds it. Building takes hundreds of milliseconds, seconds the very first time.
	 */
	FContextPtr AcquireContext(FIntPoint OutputSize);

	/**
	 * Render thread: the scene color reaching the upscaler is in this format (an MTLPixelFormat). When it is not the one the scaler
	 * was built for the next game frames switch to (and build, once) a scaler for it; the frames already in the pipeline get the
	 * bilinear fallback.
	 */
	void NoteColorFormat(uint32 ColorFormat);

	/**
	 * Game thread: the game's main view is rendered without MetalFX this frame (TSR or no temporal upscaling). The MetalFX history,
	 * if any, is stale when we come back, and the reason (a string literal) is what astra.metalfx.status says while it lasts.
	 */
	void NoteDeclinedFrame(const TCHAR* Reason);
	uint32 GetDeclineEpoch() const { return DeclineEpoch.load(); }

	/** Game thread: the game's main view is upscaled by MetalFX this frame. */
	void NoteUpscaledFrame(FIntPoint OutputSize);

	/** r.AstraMetalFX.Debug. Render thread. */
	AstraMetalFX::EDebugView GetDebugView() const;

	/** Render thread, once per upscaled frame: publishes the cost counters (stat, periodic log). */
	void PublishFrame(const FContextPtr& Context);

	FAstraMetalFXStatus GetStatus() const;

private:
	void StartBuild(FIntPoint OutputSize, uint32 ColorFormat);
	uint32 PredictColorFormat() const;

	bool bStarted = false;
	bool bSupported = false;
	FString UnsupportedReason;

	std::atomic<bool> bDisabled{ false };
	std::atomic<uint32> DeclineEpoch{ 0 };
	std::atomic<const TCHAR*> LastDeclineReason{ nullptr };
	std::atomic<double> LastDeclineTime{ 0.0 };
	bool bUpscalingNow = false;   // game thread: what the game view did last frame, to log the switches between MetalFX and TSR
	std::atomic<int32> BuildsInFlight{ 0 };
	std::atomic<uint32> WantedColorFormat{ 0 };   // MTLPixelFormat of the scene color the scalers are wanted for

	mutable FCriticalSection Lock;   // guards everything below
	TArray<FContextPtr> Contexts;   // the scalers built for the current output size, one per scene color format seen
	FContextPtr LastUsed;          // the one the last upscaled frame used (status and timings)
	bool bBuilding = false;
	FString DisabledReason;
	bool bActiveLastFrame = false;
	double LastActiveTime = 0.0;
	double LastLogTime = 0.0;

	TSharedPtr<FAstraMetalFXViewExtension, ESPMode::ThreadSafe> ViewExtension;
};
