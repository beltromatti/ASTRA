// Copyright ASTRA. The plugin's state: cvars, the scaler context (built on a worker thread, swapped in when ready), the
// fallback latch, the cost counters. One instance, owned by the module, used by the view extension (game thread) and the
// upscaler (render thread).

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
	 * Game thread, when a game view wants MetalFX: the scaler for this output size if it is ready, else null (TSR this
	 * frame) and a worker thread builds it. Building takes hundreds of milliseconds, seconds the very first time.
	 */
	FContextPtr AcquireContext(FIntPoint OutputSize);

	/** The game view is rendered without MetalFX this frame: the MetalFX history, if any, is stale when we come back. */
	void NoteDeclinedFrame() { DeclineEpoch.fetch_add(1); }
	uint32 GetDeclineEpoch() const { return DeclineEpoch.load(); }

	/** r.AstraMetalFX.Debug. Render thread. */
	AstraMetalFX::EDebugView GetDebugView() const;

	/** Render thread, once per upscaled frame: publishes the cost counters (stat, periodic log). */
	void PublishFrame(const FContextPtr& Context);

	FAstraMetalFXStatus GetStatus() const;

private:
	void StartBuild(FIntPoint OutputSize);

	bool bStarted = false;
	bool bSupported = false;
	FString UnsupportedReason;

	std::atomic<bool> bDisabled{ false };
	std::atomic<uint32> DeclineEpoch{ 0 };
	std::atomic<int32> BuildsInFlight{ 0 };

	mutable FCriticalSection Lock;   // guards everything below
	FContextPtr Current;
	bool bBuilding = false;
	FString DisabledReason;
	bool bActiveLastFrame = false;
	double LastActiveTime = 0.0;
	double LastLogTime = 0.0;

	TSharedPtr<FAstraMetalFXViewExtension, ESPMode::ThreadSafe> ViewExtension;
};
