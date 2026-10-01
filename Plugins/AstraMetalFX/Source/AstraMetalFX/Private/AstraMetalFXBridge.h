// Copyright ASTRA. The only door to Metal and MetalFX: plain C++ types on this side (no Objective-C, no Metal headers),
// everything Metal-specific lives in AstraMetalFXBridge.mm. Mac only; the header is harmless elsewhere but never built there.

#pragma once

#include "CoreMinimal.h"

class FRHITexture;

namespace AstraMetalFX
{
	/** What the optional visualisation (r.AstraMetalFX.Debug) writes into the output instead of the upscaled image. */
	enum class EDebugView : uint8
	{
		Off = 0,
		Motion = 1,    // the motion vectors the upscaler gets, as colour (hue = direction, brightness = length)
		Dynamic = 2    // which pixels take their motion from the velocity buffer (moving objects) instead of the camera
	};

	/** Why MetalFX cannot run on this machine, or an empty string when it can. Needs the Metal RHI to be up. */
	FString QueryUnsupportedReason();

	/**
	 * Scene color formats are MTLPixelFormat values (a uint32 here, this header has no Metal). The ones the scaler is built for:
	 * RGBA16F (r.SceneColorFormat 4, sg.EffectsQuality 3), R11G11B10F (3, the lower levels) and RGB10A2 (1).
	 */
	bool SupportsColorFormat(uint32 ColorFormat);
	uint32 DefaultColorFormat();
	FString ColorFormatName(uint32 ColorFormat);

	/**
	 * Where the plugin spends CPU time in a frame, as exponential averages in microseconds. None of these stages waits for the GPU:
	 * the flush only hands the recorded work to the RHI thread (the renderer does it itself at its dispatch hints), the submission
	 * is a call that enqueues a payload, the encoding takes tens of microseconds. astra.metalfx.status prints them.
	 */
	enum class ECpuStage : uint8
	{
		Pass,     // the whole RDG pass of the upscaler, render thread
		Flush,    // ...of which RHICmdList.ImmediateFlush(DispatchToRHIThread)
		Submit,   // FScalerContext::Submit, RHI thread
		Encode    // encoding and committing the Metal command buffer, Metal submission thread
	};
	void NoteCpuTime(ECpuStage Stage, double Microseconds);

	struct FCpuTimings
	{
		float PassUs = 0.0f;
		float FlushUs = 0.0f;
		float SubmitUs = 0.0f;
		float EncodeUs = 0.0f;
	};
	FCpuTimings GetCpuTimings();

	/** One frame of work for the upscaler, all plain data. The textures are the RHI's; the bridge retains their native handles. */
	struct FFrame
	{
		FRHITexture* SceneColor = nullptr;      // the rendered rectangle starts at ViewRect.Min
		FRHITexture* SceneDepth = nullptr;      // depth / stencil, reversed Z
		FRHITexture* SceneVelocity = nullptr;   // Unreal's encoded velocity (may be null or a dummy)
		FRHITexture* EyeAdaptation = nullptr;   // 1x1, the exposure of the tonemapper in x (may be null)
		FRHITexture* Output = nullptr;          // RGBA16F, OutputSize, shader read/write and render target
		FIntRect ViewRect = FIntRect(0, 0, 0, 0);
		FIntPoint OutputSize = FIntPoint::ZeroValue;
		FVector2f Jitter = FVector2f::ZeroVector;   // Unreal's TemporalJitterPixels, passed as it is
		float PreExposure = 1.0f;
		float ClipToPrevClip[16] = {};              // Unreal's matrix, row-major, copied verbatim
		bool bReset = false;                        // history invalid: camera cut, first frame, ...
		bool bFallback = false;                     // the scene color is not in the scaler's format: bilinear stretch instead of MetalFX
		EDebugView DebugView = EDebugView::Off;
		uint64 FrameNumber = 0;
	};

	/** What the last completed frames cost on the GPU, reported by the Metal completion handlers. */
	struct FGpuTimings
	{
		float LastMs = 0.0f;
		float AverageMs = 0.0f;
		uint64 Frames = 0;
		uint64 Errors = 0;
		uint64 Fallbacks = 0;   // frames that got the bilinear fallback
	};

	/**
	 * One MetalFX temporal scaler tied to an output size, with its private textures and Metal pipelines.
	 * Creating it is slow (hundreds of milliseconds, seconds the first time the machine ever compiles the scaler's
	 * pipelines): do it on a worker thread, never on the render thread. Submit() is cheap.
	 */
	class FScalerContext
	{
	public:
		struct FImpl;   // Metal objects and state, opaque here

		FScalerContext(const FScalerContext&) = delete;
		FScalerContext& operator=(const FScalerContext&) = delete;
		~FScalerContext();

		FIntPoint GetOutputSize() const { return OutputSize; }

		/** The scene color format (MTLPixelFormat) this scaler was built for: a frame in another one cannot use it. */
		uint32 GetColorFormat() const { return ColorFormat; }

		/** Smallest and largest (rendered size / output size) the scaler accepts: what dynamic resolution may use. */
		float GetMinInputFraction() const { return MinInputFraction; }
		float GetMaxInputFraction() const { return MaxInputFraction; }

		/** True until a frame fails (Metal command buffer error, unexpected texture format, ...). */
		bool IsHealthy() const;
		FString GetFailureReason() const;

		/**
		 * RHI thread, inside an RHICmdList.EnqueueLambda that follows RHICmdList.ImmediateFlush(DispatchToRHIThread): everything
		 * recorded before is already handed to Metal, so the command buffer this encodes lands between Unreal's own in queue
		 * order. The work runs on the RHI's Metal submission thread through IMetalDynamicRHI::RHIRunOnQueue.
		 */
		void Submit(const FFrame& Frame);

		FGpuTimings GetTimings() const;

	private:
		friend TSharedPtr<FScalerContext, ESPMode::ThreadSafe> CreateScalerContext(FIntPoint OutputSize, uint32 ColorFormat, FString& OutError);
		FScalerContext(FIntPoint InOutputSize, uint32 InColorFormat);

		FIntPoint OutputSize;
		uint32 ColorFormat;
		float MinInputFraction = 1.0f;
		float MaxInputFraction = 1.0f;

		TSharedPtr<FImpl, ESPMode::ThreadSafe> Impl;   // shared with the Metal completion handlers, which may outlive the context
	};

	/** Creates the scaler for an output size and a scene color format. Slow, worker thread. Returns null (and a reason) on failure. */
	TSharedPtr<FScalerContext, ESPMode::ThreadSafe> CreateScalerContext(FIntPoint OutputSize, uint32 ColorFormat, FString& OutError);

	/** Shutdown: returns once the Metal submission thread has run every callback handed to it before this call. */
	void DrainSubmissionQueue();

	/** Shutdown: wait (up to the timeout) for the command buffers already committed to complete on the GPU. */
	void WaitForCommandBuffers(double TimeoutSeconds);

	/** Shutdown: drop the process-wide Metal objects (the compiled kernel library). */
	void ReleaseSharedResources();
}
