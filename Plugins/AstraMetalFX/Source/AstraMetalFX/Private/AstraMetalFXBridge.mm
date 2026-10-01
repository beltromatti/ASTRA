// Copyright ASTRA. The Unreal side of the Metal bridge (Objective-C++, ARC on): turns Unreal's RHI textures into native
// Metal textures and runs AstraMetalFXCore's encoding on the RHI's own Metal queue, in the right place of the frame.
//
// How a frame runs (see docs/ricerca/15-metalfx.md):
//  - the renderer's RDG pass flushes Unreal's recorded work to the RHI thread, then enqueues an RHI lambda that calls
//    FScalerContext::Submit here. Because the flush closed the previous submission, Metal's payload queue already holds
//    everything Unreal recorded up to this point;
//  - Submit hands the native textures to IMetalDynamicRHI::RHIRunOnQueue. Its callback runs on the RHI's Metal submission
//    thread, in payload order: the core creates its own command buffer on the very queue Unreal uses, encodes the motion
//    kernel and MetalFX into it and commits it. Unreal's command buffers before and after ours are ordered against it by
//    Metal's hazard tracking (Unreal allocates its textures from tracked heaps: the core checks that), no event needed;
//  - nothing slow may run in the callback (it blocks Metal's submission thread): the scaler, the pipelines and the private
//    textures are built beforehand by CreateScalerContext, on a worker thread.

#include "AstraMetalFXBridge.h"

#if PLATFORM_MAC

// IMetalDynamicRHI.h first: through Mac/MacSystemIncludes.h it pulls Carbon and CoreServices in with the FVector workaround,
// which Foundation (imported by the core header) would otherwise collide with.
#include "IMetalDynamicRHI.h"
#include "AstraMetalFXCore.h"
#include "AstraMetalFXModule.h"
#include "HAL/PlatformProcess.h"
#include "HAL/PlatformTime.h"
#include "RHI.h"
#include "RHIResources.h"

#include <atomic>
#include <mutex>

namespace AstraMetalFX
{
	struct FScalerContext::FImpl
	{
		std::shared_ptr<Core::FScaler> Scaler;
	};

	namespace
	{
		void EnsureLogger()
		{
			static std::once_flag Once;
			std::call_once(Once, []()
			{
				Core::SetLogger([](Core::ELogLevel Level, const std::string& Text)
				{
					const FString Message = UTF8_TO_TCHAR(Text.c_str());
					switch (Level)
					{
					case Core::ELogLevel::Warning: UE_LOG(LogAstraMetalFX, Warning, TEXT("%s"), *Message); break;
					case Core::ELogLevel::Error: UE_LOG(LogAstraMetalFX, Error, TEXT("%s"), *Message); break;
					default: UE_LOG(LogAstraMetalFX, Log, TEXT("%s"), *Message); break;
					}
				});
			});
		}

		// The RHI textures of one frame. The RHI places its textures in heaps it manages itself and hands the memory of a texture to
		// the next one as soon as the first is destroyed; our command buffer is unknown to it, so the textures are kept alive
		// until the GPU has completed that command buffer (the core releases this from its completion handler).
		struct FKeepAlive
		{
			TRefCountPtr<FRHITexture> Textures[5];
		};

		id<MTLDevice> GetDevice()
		{
			if (!IsRHIMetal())
			{
				return nil;
			}
			return (__bridge id<MTLDevice>)GetIMetalDynamicRHI()->RHIGetDevice();
		}

		FString ToFString(const std::string& Text)
		{
			return FString(UTF8_TO_TCHAR(Text.c_str()));
		}
	}

	bool SupportsColorFormat(uint32 ColorFormat)
	{
		return Core::SupportsColorFormat((MTLPixelFormat)ColorFormat);
	}

	uint32 DefaultColorFormat()
	{
		return (uint32)MTLPixelFormatRGBA16Float;
	}

	FString ColorFormatName(uint32 ColorFormat)
	{
		switch ((MTLPixelFormat)ColorFormat)
		{
		case MTLPixelFormatRGBA16Float: return TEXT("RGBA16F");
		case MTLPixelFormatRG11B10Float: return TEXT("R11G11B10F");
		case MTLPixelFormatRGB10A2Unorm: return TEXT("RGB10A2");
		default: return FString::Printf(TEXT("MTLPixelFormat %u"), ColorFormat);
		}
	}

	FString QueryUnsupportedReason()
	{
		@autoreleasepool
		{
			EnsureLogger();
			if (!IsRHIMetal())
			{
				return TEXT("the RHI is not Metal");
			}
			return ToFString(Core::FScaler::QueryUnsupportedReason(GetDevice()));
		}
	}

	FScalerContext::FScalerContext(FIntPoint InOutputSize, uint32 InColorFormat)
		: OutputSize(InOutputSize)
		, ColorFormat(InColorFormat)
	{
	}

	FScalerContext::~FScalerContext() = default;

	bool FScalerContext::IsHealthy() const
	{
		return Impl.IsValid() && Impl->Scaler && !Impl->Scaler->Failed();
	}

	FString FScalerContext::GetFailureReason() const
	{
		return Impl.IsValid() && Impl->Scaler ? ToFString(Impl->Scaler->FailureReason()) : FString(TEXT("no scaler"));
	}

	FGpuTimings FScalerContext::GetTimings() const
	{
		FGpuTimings Result;
		if (Impl.IsValid() && Impl->Scaler)
		{
			const Core::FTimings Timings = Impl->Scaler->Timings();
			Result.LastMs = Timings.LastMs;
			Result.AverageMs = Timings.AverageMs;
			Result.Frames = Timings.Frames;
			Result.Errors = Timings.Errors;
			Result.Fallbacks = Timings.Fallbacks;
		}
		return Result;
	}

	TSharedPtr<FScalerContext, ESPMode::ThreadSafe> CreateScalerContext(FIntPoint OutputSize, uint32 ColorFormat, FString& OutError)
	{
		@autoreleasepool
		{
			EnsureLogger();
			if (!IsRHIMetal())
			{
				OutError = TEXT("the RHI is not Metal");
				return nullptr;
			}

			std::string Error;
			std::shared_ptr<Core::FScaler> Scaler = Core::FScaler::Create(GetDevice(), OutputSize.X, OutputSize.Y, (MTLPixelFormat)ColorFormat, Error);
			if (!Scaler)
			{
				OutError = ToFString(Error);
				return nullptr;
			}

			TSharedPtr<FScalerContext, ESPMode::ThreadSafe> Context = MakeShareable(new FScalerContext(OutputSize, ColorFormat));
			Context->Impl = MakeShared<FScalerContext::FImpl, ESPMode::ThreadSafe>();
			Context->Impl->Scaler = Scaler;
			Context->MinInputFraction = 1.0f / Scaler->MaxScale();
			Context->MaxInputFraction = 1.0f / Scaler->MinScale();
			return Context;
		}
	}

	void FScalerContext::Submit(const FFrame& Frame)
	{
		@autoreleasepool
		{
			if (!Impl.IsValid() || !Impl->Scaler || !IsRHIMetal())
			{
				return;
			}

			// The native Metal texture behind an RHI texture (FRHITexture::GetNativeResource: "designed to provide plugins with
			// access to the underlying resource"). Retained by the frame input until the GPU has completed the command buffer.
			auto Native = [](FRHITexture* Texture) -> id<MTLTexture> { return Texture ? (__bridge id<MTLTexture>)Texture->GetNativeResource() : nil; };

			std::shared_ptr<FKeepAlive> Keep = std::make_shared<FKeepAlive>();
			Keep->Textures[0] = Frame.SceneColor;
			Keep->Textures[1] = Frame.SceneDepth;
			Keep->Textures[2] = Frame.SceneVelocity;
			Keep->Textures[3] = Frame.EyeAdaptation;
			Keep->Textures[4] = Frame.Output;

			// A frame the scaler cannot process (another scene color format than it was built for, a scaler that failed, frames already in
			// the pipeline when that was noticed) still owes the renderer a valid image: the core's bilinear stretch of the rendered
			// rectangle, black if even that is impossible. The host switches the game view to TSR soon after.
			auto FallbackInstead = [this, &Frame, &Native, Keep]()
			{
				std::shared_ptr<Core::FFrameInput> Stretch = std::make_shared<Core::FFrameInput>();
				Stretch->Color = Native(Frame.SceneColor);
				Stretch->Output = Native(Frame.Output);
				Stretch->ViewMinX = (uint32_t)FMath::Max(Frame.ViewRect.Min.X, 0);
				Stretch->ViewMinY = (uint32_t)FMath::Max(Frame.ViewRect.Min.Y, 0);
				Stretch->ViewW = (uint32_t)FMath::Max(Frame.ViewRect.Width(), 0);
				Stretch->ViewH = (uint32_t)FMath::Max(Frame.ViewRect.Height(), 0);
				Stretch->KeepAlive = Keep;
				if (Stretch->Output)
				{
					std::shared_ptr<Core::FScaler> Scaler = Impl->Scaler;
					std::shared_ptr<const Core::FFrameInput> ConstStretch = Stretch;
					GetIMetalDynamicRHI()->RHIRunOnQueue([Scaler, ConstStretch](MTL::CommandQueue* Queue)
					{
						Scaler->EncodeFallback((__bridge id<MTLCommandQueue>)Queue, ConstStretch);
					}, /*bWaitForSubmission=*/false);
				}
			};
			if (Frame.bFallback || Impl->Scaler->Failed())
			{
				FallbackInstead();
				return;
			}

			std::shared_ptr<Core::FFrameInput> Input = std::make_shared<Core::FFrameInput>();
			Input->Color = Native(Frame.SceneColor);
			Input->Depth = Native(Frame.SceneDepth);
			Input->Velocity = Native(Frame.SceneVelocity);
			Input->Eye = Native(Frame.EyeAdaptation);
			Input->Output = Native(Frame.Output);
			Input->ViewMinX = (uint32_t)FMath::Max(Frame.ViewRect.Min.X, 0);
			Input->ViewMinY = (uint32_t)FMath::Max(Frame.ViewRect.Min.Y, 0);
			Input->ViewW = (uint32_t)FMath::Max(Frame.ViewRect.Width(), 0);
			Input->ViewH = (uint32_t)FMath::Max(Frame.ViewRect.Height(), 0);
			Input->JitterX = Frame.Jitter.X;
			Input->JitterY = Frame.Jitter.Y;
			Input->PreExposure = Frame.PreExposure;
			FMemory::Memcpy(Input->ClipToPrevClip, Frame.ClipToPrevClip, sizeof(Input->ClipToPrevClip));
			Input->bReset = Frame.bReset;
			Input->Debug = (Core::EDebugMode)Frame.DebugView;
			Input->KeepAlive = Keep;

			const std::string Problem = Impl->Scaler->Validate(*Input);
			if (!Problem.empty())
			{
				Impl->Scaler->Fail(Problem);
				FallbackInstead();
				return;
			}

			std::shared_ptr<Core::FScaler> Scaler = Impl->Scaler;
			std::shared_ptr<const Core::FFrameInput> ConstInput = Input;
			GetIMetalDynamicRHI()->RHIRunOnQueue([Scaler, ConstInput](MTL::CommandQueue* Queue)
			{
				@autoreleasepool
				{
					const double Start = FPlatformTime::Seconds();
					Scaler->Encode((__bridge id<MTLCommandQueue>)Queue, ConstInput);
					// Encoding takes tens of microseconds; anything slower stalls the Metal submission thread, and with it the GPU.
					const double Ms = (FPlatformTime::Seconds() - Start) * 1000.0;
					static std::atomic<int> Reports{ 0 };
					if (Ms > 4.0 && Reports.fetch_add(1) < 8)
					{
						UE_LOG(LogAstraMetalFX, Warning, TEXT("encoding a MetalFX frame took %.1f ms on the Metal submission thread"), Ms);
					}
				}
			}, /*bWaitForSubmission=*/false);
		}
	}

	void DrainSubmissionQueue()
	{
		if (IsRHIMetal())
		{
			GetIMetalDynamicRHI()->RHIRunOnQueue([](MTL::CommandQueue*) {}, /*bWaitForSubmission=*/true);
		}
	}

	void WaitForCommandBuffers(double TimeoutSeconds)
	{
		const double Start = FPlatformTime::Seconds();
		while (Core::FScaler::CommandBuffersInFlight() > 0 && FPlatformTime::Seconds() - Start < TimeoutSeconds)
		{
			FPlatformProcess::Sleep(0.002f);
		}
	}

	void ReleaseSharedResources()
	{
		Core::FScaler::ReleaseSharedResources();
	}
}

#endif // PLATFORM_MAC
