// Copyright ASTRA. The Metal / MetalFX half of the plugin with no dependency on Unreal (Objective-C++, ARC): the scaler,
// the kernels that prepare Unreal's frame for it, the checks of the textures and the command buffer encoding. The Unreal side
// (AstraMetalFXBridge.mm) hands it native textures and a queue; tools/metalfx_probe/probe_core.mm drives the same code
// offline with synthetic frames, which is how the plugin is tested without the game.
//
// Include from Objective-C++ only.

#pragma once

#import <Metal/Metal.h>
#import <MetalFX/MetalFX.h>

#include <atomic>
#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
#include <string>

namespace AstraMetalFX
{
namespace Core
{
	enum class ELogLevel { Log, Warning, Error };

	/** Where the core reports what it does (the host forwards to its own log). Set once, before any other call. */
	void SetLogger(std::function<void(ELogLevel, const std::string&)> Logger);

	/** What the optional visualisation writes into the output instead of the upscaled image. */
	enum class EDebugMode : uint32_t { Off = 0, Motion = 1, Dynamic = 2 };

	/** One frame of work. Textures may be null where noted; all of them are retained until the command buffer has completed. */
	struct FFrameInput
	{
		id<MTLTexture> Color = nil;       // RGBA16F; the rendered rectangle starts at (ViewMinX, ViewMinY)
		id<MTLTexture> Depth = nil;       // Depth32Float_Stencil8, reversed Z
		id<MTLTexture> Velocity = nil;    // Unreal's encoded velocity; null: camera motion only
		id<MTLTexture> Eye = nil;         // eye adaptation, 1x1, exposure in x; null: neutral exposure
		id<MTLTexture> Output = nil;      // RGBA16F, exactly the scaler's output size
		uint32_t ViewMinX = 0, ViewMinY = 0, ViewW = 0, ViewH = 0;
		float JitterX = 0.0f, JitterY = 0.0f;   // pixels of the rendered rectangle, Unreal's TemporalJitterPixels
		float PreExposure = 1.0f;
		float ClipToPrevClip[16] = {};          // Unreal's ClipToPrevClip, row-major, verbatim
		bool bReset = false;
		EDebugMode Debug = EDebugMode::Off;

		/**
		 * Whatever the host needs to stay alive until the GPU has finished with the frame (the Unreal RHI textures: the RHI
		 * recycles the memory of a texture the moment it is destroyed and does not know about our command buffer). Released by
		 * the command buffer's completion handler, on a Metal thread, together with the rest of the frame.
		 */
		std::shared_ptr<void> KeepAlive;
	};

	struct FTimings
	{
		float LastMs = 0.0f;
		float AverageMs = 0.0f;
		uint64_t Frames = 0;
		uint64_t Errors = 0;
	};

	/**
	 * Fills a texture with black (a render pass clear, the texture needs the render target usage): what the host's frame gets
	 * instead of an upscaled image when the scaler cannot run, so the tonemapper never reads uninitialised memory.
	 * KeepAlive is released when the GPU has completed the clear (see FFrameInput::KeepAlive).
	 */
	void ClearTexture(id<MTLCommandQueue> Queue, id<MTLTexture> Texture, std::shared_ptr<void> KeepAlive = nullptr);

	/** A MetalFX temporal scaler for one output size with its private textures and kernels. Creating it is slow: a worker thread. */
	class FScaler : public std::enable_shared_from_this<FScaler>
	{
	public:
		/** Null (and a reason) when MetalFX or the kernels cannot be built. Slow: hundreds of milliseconds, seconds the first time. */
		static std::shared_ptr<FScaler> Create(id<MTLDevice> Device, int OutputW, int OutputH, std::string& OutError);

		/** Empty when the device supports MetalFX temporal scaling, else why not. Cheap. */
		static std::string QueryUnsupportedReason(id<MTLDevice> Device);

		~FScaler();

		int OutputW() const { return OutputW_; }
		int OutputH() const { return OutputH_; }
		float MinScale() const { return MinScale_; }   // smallest and largest output / rendered size the scaler accepts
		float MaxScale() const { return MaxScale_; }

		/** Empty when the frame's textures fit what the scaler and its ordering trick need, else the first problem. Cheap. */
		std::string Validate(const FFrameInput& Frame) const;

		/**
		 * Encodes the frame into a new command buffer of Queue and commits it. Fast (tens of microseconds). The scaler's state
		 * is used by one call at a time, in frame order: call it from one thread, or from a serial submission queue.
		 * The frame (and so its textures) stays alive until the GPU has completed the command buffer.
		 */
		void Encode(id<MTLCommandQueue> Queue, const std::shared_ptr<const FFrameInput>& Frame);

		bool Failed() const { return bFailed_.load(); }
		std::string FailureReason() const;
		/** Marks the scaler failed (once): the host falls back to its own upscaler. */
		void Fail(const std::string& Reason);

		FTimings Timings() const;

		/** Number of command buffers committed and not yet completed, process-wide (shutdown waits for zero). */
		static int CommandBuffersInFlight();

		/** Drops the process-wide compiled kernel library. */
		static void ReleaseSharedResources();

	private:
		FScaler() = default;
		FScaler(const FScaler&) = delete;
		FScaler& operator=(const FScaler&) = delete;

		int OutputW_ = 0, OutputH_ = 0;
		float MinScale_ = 1.0f, MaxScale_ = 3.0f;
		uint32_t Id_ = 0;

		id<MTLFXTemporalScaler> Scaler_ = nil;
		id<MTLComputePipelineState> MotionPipeline_ = nil;
		id<MTLComputePipelineState> ExposurePipeline_ = nil;
		id<MTLComputePipelineState> DebugPipeline_ = nil;
		id<MTLTexture> MotionTexture_ = nil;     // what the scaler reads as motion vectors, as big as the color texture it goes with
		id<MTLTexture> ExposureTexture_ = nil;   // 1x1 R16F
		id<MTLTexture> DummyVelocity_ = nil;     // bound when there is no velocity texture
		id<MTLTexture> DummyEye_ = nil;          // same for the eye adaptation texture
		id<MTLTexture> ColorCopy_ = nil;         // a view that does not start at the textures' corner (letterboxing) has its rectangle of
		id<MTLTexture> DepthCopy_ = nil;         // color and depth copied to these, of the output's size, for the scaler

		std::atomic<bool> bFailed_{ false };
		mutable std::mutex Mutex_;               // guards FailureReason_ and Timings_
		std::string FailureReason_;
		FTimings Timings_;
		bool bWarnedScale_ = false;
	};
}
}
