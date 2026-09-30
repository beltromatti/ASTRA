// Copyright ASTRA. See AstraMetalFXCore.h.

#import "AstraMetalFXCore.h"

#include <algorithm>
#include <cmath>
#include <cstdarg>
#include <cstdio>
#include <cstring>

#include "AstraMetalFXKernels.inl"

namespace AstraMetalFX
{
namespace Core
{
	namespace
	{
		// Mirrors AstraParams in AstraMetalFXKernels.inl (112 bytes, all 4-byte members).
		struct FAstraParams
		{
			float ClipToPrevClip[16];
			uint32_t ViewRectMin[2];
			uint32_t ViewSize[2];
			uint32_t VelocityExtent[2];
			float ScreenToPixel[2];
			float ExposureFallback;
			uint32_t Flags;
			uint32_t DebugMode;
			uint32_t Pad;
		};
		static_assert(sizeof(FAstraParams) == 112, "FAstraParams must match AstraParams in AstraMetalFXKernels.inl");

		constexpr uint32_t kFlagIgnoreVelocity = 1u;
		constexpr uint32_t kFlagEyeAdaptation = 4u;

		// Formats the scaler is built for: Unreal's scene color, scene depth and the plugin's own motion texture.
		constexpr MTLPixelFormat kColorFormat = MTLPixelFormatRGBA16Float;
		constexpr MTLPixelFormat kDepthFormat = MTLPixelFormatDepth32Float_Stencil8;
		constexpr MTLPixelFormat kMotionFormat = MTLPixelFormatRG16Float;
		constexpr MTLPixelFormat kOutputFormat = MTLPixelFormatRGBA16Float;

		std::atomic<uint32_t> GNextId{ 1 };
		std::atomic<int> GInFlight{ 0 };

		std::function<void(ELogLevel, const std::string&)> GLogger;

		void Log(ELogLevel Level, const std::string& Text)
		{
			if (GLogger)
			{
				GLogger(Level, Text);
			}
		}

		std::string Str(NSString* Text)
		{
			return Text ? std::string([Text UTF8String]) : std::string();
		}

		// The compiled kernels, once per process (a few tens of milliseconds).
		id<MTLLibrary> GLibrary = nil;
		std::mutex GLibraryMutex;

		id<MTLLibrary> GetLibrary(id<MTLDevice> Device, std::string& OutError)
		{
			std::lock_guard<std::mutex> Lock(GLibraryMutex);
			if (!GLibrary)
			{
				NSError* Error = nil;
				GLibrary = [Device newLibraryWithSource:[NSString stringWithUTF8String:kAstraMetalFXKernelSource] options:[MTLCompileOptions new] error:&Error];
				if (!GLibrary)
				{
					OutError = "the Metal kernels do not compile: " + Str(Error.localizedDescription);
				}
			}
			return GLibrary;
		}

		id<MTLComputePipelineState> MakePipeline(id<MTLDevice> Device, id<MTLLibrary> Library, NSString* Name, std::string& OutError)
		{
			NSError* Error = nil;
			id<MTLFunction> Function = [Library newFunctionWithName:Name];
			id<MTLComputePipelineState> Pipeline = Function ? [Device newComputePipelineStateWithFunction:Function error:&Error] : nil;
			if (!Pipeline)
			{
				OutError = "the Metal kernel " + Str(Name) + " cannot be built: " + Str(Error.localizedDescription);
			}
			return Pipeline;
		}

		id<MTLTexture> MakeTexture(id<MTLDevice> Device, MTLPixelFormat Format, NSUInteger Width, NSUInteger Height, MTLTextureUsage Usage, NSString* Label)
		{
			MTLTextureDescriptor* Desc = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:Format width:Width height:Height mipmapped:NO];
			Desc.usage = Usage;
			Desc.storageMode = MTLStorageModePrivate;
			id<MTLTexture> Texture = [Device newTextureWithDescriptor:Desc];
			Texture.label = Label;
			return Texture;
		}

		std::string Format(const char* Fmt, ...) __attribute__((format(printf, 1, 2)));
		std::string Format(const char* Fmt, ...)
		{
			char Buffer[512];
			va_list Args;
			va_start(Args, Fmt);
			vsnprintf(Buffer, sizeof(Buffer), Fmt, Args);
			va_end(Args);
			return Buffer;
		}
	}

	void SetLogger(std::function<void(ELogLevel, const std::string&)> Logger)
	{
		GLogger = std::move(Logger);
	}

	std::string FScaler::QueryUnsupportedReason(id<MTLDevice> Device)
	{
		@autoreleasepool
		{
			if (!Device)
			{
				return "there is no Metal device";
			}
			if (NSClassFromString(@"MTLFXTemporalScalerDescriptor") == nil)
			{
				return "the MetalFX framework is not available on this macOS";
			}
			if (![MTLFXTemporalScalerDescriptor supportsDevice:Device])
			{
				return "the GPU (" + Str(Device.name) + ") does not support MetalFX temporal scaling";
			}
			return std::string();
		}
	}

	FScaler::~FScaler() = default;

	std::shared_ptr<FScaler> FScaler::Create(id<MTLDevice> Device, int OutputW, int OutputH, std::string& OutError)
	{
		@autoreleasepool
		{
			OutError = QueryUnsupportedReason(Device);
			if (!OutError.empty())
			{
				return nullptr;
			}
			if (OutputW < 16 || OutputH < 16)
			{
				OutError = "the output is too small";
				return nullptr;
			}

			std::shared_ptr<FScaler> Self(new FScaler());
			Self->Id_ = GNextId.fetch_add(1);
			Self->OutputW_ = OutputW;
			Self->OutputH_ = OutputH;

			if (@available(macOS 14.0, *))
			{
				Self->MinScale_ = [MTLFXTemporalScalerDescriptor supportedInputContentMinScaleForDevice:Device];
				Self->MaxScale_ = [MTLFXTemporalScalerDescriptor supportedInputContentMaxScaleForDevice:Device];
			}
			if (!(Self->MinScale_ >= 1.0f && Self->MaxScale_ >= Self->MinScale_))
			{
				Self->MinScale_ = 1.0f;
				Self->MaxScale_ = 3.0f;
			}

			// The descriptor's input size is the largest rendered size: the output itself (scale 1). Unreal allocates its scene
			// textures at the upper bound of the dynamic resolution, bigger than the rendered rectangle and than the output;
			// MetalFX only looks at the rectangle (tools/metalfx_probe/probe_quality.mm "layout": the same image).
			MTLFXTemporalScalerDescriptor* Desc = [MTLFXTemporalScalerDescriptor new];
			Desc.colorTextureFormat = kColorFormat;
			Desc.depthTextureFormat = kDepthFormat;
			Desc.motionTextureFormat = kMotionFormat;
			Desc.outputTextureFormat = kOutputFormat;
			Desc.inputWidth = (NSUInteger)OutputW;
			Desc.inputHeight = (NSUInteger)OutputH;
			Desc.outputWidth = (NSUInteger)OutputW;
			Desc.outputHeight = (NSUInteger)OutputH;
			Desc.autoExposureEnabled = NO;
			Desc.inputContentPropertiesEnabled = YES;
			Desc.inputContentMinScale = Self->MinScale_;
			Desc.inputContentMaxScale = Self->MaxScale_;
			// A worker thread: have the scaler fully compiled before its first frame instead of running slower while MetalFX
			// compiles it in the background.
			Desc.requiresSynchronousInitialization = YES;

			Self->Scaler_ = [Desc newTemporalScalerWithDevice:Device];
			if (!Self->Scaler_)
			{
				OutError = "MetalFX could not create the temporal scaler";
				return nullptr;
			}

			id<MTLLibrary> Library = GetLibrary(Device, OutError);
			if (!Library)
			{
				return nullptr;
			}
			Self->MotionPipeline_ = MakePipeline(Device, Library, @"astra_motion", OutError);
			Self->ExposurePipeline_ = MakePipeline(Device, Library, @"astra_exposure", OutError);
			Self->DebugPipeline_ = MakePipeline(Device, Library, @"astra_debug", OutError);
			if (!Self->MotionPipeline_ || !Self->ExposurePipeline_ || !Self->DebugPipeline_)
			{
				return nullptr;
			}

			const MTLTextureUsage ReadWrite = MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite;
			Self->MotionTexture_ = MakeTexture(Device, kMotionFormat, OutputW, OutputH, ReadWrite, @"AstraMetalFX motion");
			Self->ExposureTexture_ = MakeTexture(Device, MTLPixelFormatR16Float, 1, 1, ReadWrite, @"AstraMetalFX exposure");
			Self->DummyVelocity_ = MakeTexture(Device, MTLPixelFormatRGBA16Unorm, 1, 1, MTLTextureUsageShaderRead, @"AstraMetalFX dummy velocity");
			Self->DummyEye_ = MakeTexture(Device, MTLPixelFormatRGBA32Float, 1, 1, MTLTextureUsageShaderRead, @"AstraMetalFX dummy eye adaptation");
			if (!Self->MotionTexture_ || !Self->ExposureTexture_ || !Self->DummyVelocity_ || !Self->DummyEye_)
			{
				OutError = "the private textures cannot be allocated";
				return nullptr;
			}

			Log(ELogLevel::Log, Format("MetalFX scaler %u ready: output %dx%d, rendered size from %.0f%% to %.0f%% of it, device %s",
				Self->Id_, OutputW, OutputH, 100.0f / Self->MaxScale_, 100.0f / Self->MinScale_, Str(Device.name).c_str()));
			return Self;
		}
	}

	std::string FScaler::FailureReason() const
	{
		std::lock_guard<std::mutex> Lock(Mutex_);
		return FailureReason_;
	}

	void FScaler::Fail(const std::string& Reason)
	{
		{
			std::lock_guard<std::mutex> Lock(Mutex_);
			if (FailureReason_.empty())
			{
				FailureReason_ = Reason;
			}
		}
		if (!bFailed_.exchange(true))
		{
			Log(ELogLevel::Error, Format("MetalFX scaler %u failed, the host falls back to its own upscaler: %s", Id_, Reason.c_str()));
		}
	}

	FTimings FScaler::Timings() const
	{
		std::lock_guard<std::mutex> Lock(Mutex_);
		return Timings_;
	}

	int FScaler::CommandBuffersInFlight()
	{
		return GInFlight.load();
	}

	void FScaler::ReleaseSharedResources()
	{
		std::lock_guard<std::mutex> Lock(GLibraryMutex);
		GLibrary = nil;
	}

	std::string FScaler::Validate(const FFrameInput& Frame) const
	{
		if (!Frame.Color || !Frame.Depth || !Frame.Output)
		{
			return "a texture of the frame has no native Metal resource";
		}
		auto Tracked = [](id<MTLTexture> Texture) { return !Texture || Texture.hazardTrackingMode != MTLHazardTrackingModeUntracked; };
		if (!Tracked(Frame.Color) || !Tracked(Frame.Depth) || !Tracked(Frame.Velocity) || !Tracked(Frame.Eye) || !Tracked(Frame.Output))
		{
			// The separate command buffer relies on Metal's hazard tracking to be ordered against Unreal's: without it we would race.
			return "the frame's textures are not hazard tracked: the MetalFX command buffer cannot be ordered against the renderer's";
		}
		if (Frame.Color.textureType != MTLTextureType2D || Frame.Depth.textureType != MTLTextureType2D || Frame.Color.sampleCount != 1)
		{
			return "the scene textures are not plain 2D single-sample textures";
		}
		if (Frame.Color.pixelFormat != kColorFormat)
		{
			return Format("the scene color format (MTLPixelFormat %d) is not RGBA16F", (int)Frame.Color.pixelFormat);
		}
		if (Frame.Depth.pixelFormat != kDepthFormat)
		{
			return Format("the scene depth format (MTLPixelFormat %d) is not Depth32Float_Stencil8", (int)Frame.Depth.pixelFormat);
		}
		if (Frame.Output.pixelFormat != kOutputFormat || (int)Frame.Output.width != OutputW_ || (int)Frame.Output.height != OutputH_)
		{
			return Format("the output texture is %dx%d (format %d), the scaler was built for %dx%d RGBA16F",
				(int)Frame.Output.width, (int)Frame.Output.height, (int)Frame.Output.pixelFormat, OutputW_, OutputH_);
		}
		const MTLTextureUsage NeedOutput = Scaler_.outputTextureUsage;
		if ((Frame.Output.usage & NeedOutput) != NeedOutput)
		{
			return Format("the output texture usage %lu lacks what MetalFX needs (%lu)", (unsigned long)Frame.Output.usage, (unsigned long)NeedOutput);
		}
		if ((Frame.Color.usage & Scaler_.colorTextureUsage) != Scaler_.colorTextureUsage || (Frame.Depth.usage & Scaler_.depthTextureUsage) != Scaler_.depthTextureUsage)
		{
			return "the scene color or depth texture lacks the usage MetalFX needs";
		}
		if (Frame.ViewW < 1 || Frame.ViewH < 1 || Frame.ViewMinX + Frame.ViewW > Frame.Color.width || Frame.ViewMinY + Frame.ViewH > Frame.Color.height
			|| Frame.ViewMinX + Frame.ViewW > Frame.Depth.width || Frame.ViewMinY + Frame.ViewH > Frame.Depth.height)
		{
			return Format("the rendered rectangle (%u,%u) %ux%u does not fit the scene textures", Frame.ViewMinX, Frame.ViewMinY, Frame.ViewW, Frame.ViewH);
		}
		return std::string();
	}

	void FScaler::Encode(id<MTLCommandQueue> Queue, const std::shared_ptr<const FFrameInput>& FramePtr)
	{
		@autoreleasepool
		{
			const FFrameInput& Frame = *FramePtr;
			if (bFailed_.load())
			{
				return;
			}

			// The rendered rectangle, limited to what the scaler accepts (the host's dynamic resolution is clamped to our limits
			// beforehand, this only guards a bad input: MetalFX asserts on a scale outside its range).
			const uint32_t MinW = (uint32_t)std::ceil((float)OutputW_ / MaxScale_);
			const uint32_t MinH = (uint32_t)std::ceil((float)OutputH_ / MaxScale_);
			const uint32_t ContentW = std::min<uint32_t>(std::max<uint32_t>(Frame.ViewW, MinW), (uint32_t)OutputW_);
			const uint32_t ContentH = std::min<uint32_t>(std::max<uint32_t>(Frame.ViewH, MinH), (uint32_t)OutputH_);
			if ((ContentW != Frame.ViewW || ContentH != Frame.ViewH) && !bWarnedScale_)
			{
				bWarnedScale_ = true;
				Log(ELogLevel::Warning, Format("the rendered size %ux%u is outside what MetalFX scales to %dx%d: using %ux%u",
					Frame.ViewW, Frame.ViewH, OutputW_, OutputH_, ContentW, ContentH));
			}

			id<MTLCommandBuffer> CommandBuffer = [Queue commandBuffer];
			CommandBuffer.label = @"AstraMetalFX";

			FAstraParams Params;
			std::memset(&Params, 0, sizeof(Params));
			std::memcpy(Params.ClipToPrevClip, Frame.ClipToPrevClip, sizeof(Params.ClipToPrevClip));
			Params.ViewRectMin[0] = Frame.ViewMinX;
			Params.ViewRectMin[1] = Frame.ViewMinY;
			Params.ViewSize[0] = ContentW;
			Params.ViewSize[1] = ContentH;
			Params.VelocityExtent[0] = Frame.Velocity ? (uint32_t)Frame.Velocity.width : 0u;
			Params.VelocityExtent[1] = Frame.Velocity ? (uint32_t)Frame.Velocity.height : 0u;
			Params.ScreenToPixel[0] = (float)ContentW * 0.5f;
			Params.ScreenToPixel[1] = (float)ContentH * 0.5f;
			Params.ExposureFallback = Frame.PreExposure;   // neutral: MetalFX divides by the pre-exposure then multiplies by this
			Params.Flags = (Frame.Velocity ? 0u : kFlagIgnoreVelocity) | (Frame.Eye ? kFlagEyeAdaptation : 0u);
			Params.DebugMode = (uint32_t)Frame.Debug;

			// Motion vectors and exposure, from Unreal's depth, velocity and eye adaptation.
			{
				id<MTLComputeCommandEncoder> Encoder = [CommandBuffer computeCommandEncoder];
				Encoder.label = @"AstraMetalFX prepare";
				[Encoder setComputePipelineState:MotionPipeline_];
				[Encoder setTexture:Frame.Depth atIndex:0];
				[Encoder setTexture:(Frame.Velocity ? Frame.Velocity : DummyVelocity_) atIndex:1];
				[Encoder setTexture:MotionTexture_ atIndex:2];
				[Encoder setBytes:&Params length:sizeof(Params) atIndex:0];
				[Encoder dispatchThreads:MTLSizeMake(ContentW, ContentH, 1) threadsPerThreadgroup:MTLSizeMake(16, 16, 1)];
				[Encoder setComputePipelineState:ExposurePipeline_];
				[Encoder setTexture:(Frame.Eye ? Frame.Eye : DummyEye_) atIndex:0];
				[Encoder setTexture:ExposureTexture_ atIndex:1];
				[Encoder setBytes:&Params length:sizeof(Params) atIndex:0];
				[Encoder dispatchThreads:MTLSizeMake(1, 1, 1) threadsPerThreadgroup:MTLSizeMake(1, 1, 1)];
				[Encoder endEncoding];
			}

			// MetalFX wants the rendered rectangle at the corner of the color texture: copy it when the host's does not start there.
			id<MTLTexture> ColorInput = Frame.Color;
			if (Frame.ViewMinX != 0 || Frame.ViewMinY != 0)
			{
				if (!ColorCopy_)
				{
					ColorCopy_ = MakeTexture(Frame.Color.device, kColorFormat, (NSUInteger)OutputW_, (NSUInteger)OutputH_, MTLTextureUsageShaderRead, @"AstraMetalFX color copy");
				}
				id<MTLBlitCommandEncoder> Blit = [CommandBuffer blitCommandEncoder];
				[Blit copyFromTexture:Frame.Color sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(Frame.ViewMinX, Frame.ViewMinY, 0)
					sourceSize:MTLSizeMake(ContentW, ContentH, 1) toTexture:ColorCopy_ destinationSlice:0 destinationLevel:0 destinationOrigin:MTLOriginMake(0, 0, 0)];
				[Blit endEncoding];
				ColorInput = ColorCopy_;
			}

			id<MTLFXTemporalScaler> Scaler = Scaler_;
			Scaler.colorTexture = ColorInput;
			Scaler.depthTexture = Frame.Depth;
			Scaler.motionTexture = MotionTexture_;
			Scaler.outputTexture = Frame.Output;
			Scaler.exposureTexture = ExposureTexture_;
			Scaler.inputContentWidth = ContentW;
			Scaler.inputContentHeight = ContentH;
			Scaler.jitterOffsetX = Frame.JitterX;   // Unreal's TemporalJitterPixels and MetalFX's jitterOffset share the convention
			Scaler.jitterOffsetY = Frame.JitterY;
			Scaler.motionVectorScaleX = 1.0f;       // the motion texture is in pixels of the rendered rectangle
			Scaler.motionVectorScaleY = 1.0f;
			Scaler.preExposure = Frame.PreExposure;
			Scaler.depthReversed = YES;             // Unreal's depth: 1 near, 0 far
			Scaler.reset = Frame.bReset ? YES : NO;
			[Scaler encodeToCommandBuffer:CommandBuffer];

			if (Frame.Debug != EDebugMode::Off)
			{
				id<MTLComputeCommandEncoder> Encoder = [CommandBuffer computeCommandEncoder];
				Encoder.label = @"AstraMetalFX debug view";
				[Encoder setComputePipelineState:DebugPipeline_];
				[Encoder setTexture:Frame.Depth atIndex:0];
				[Encoder setTexture:(Frame.Velocity ? Frame.Velocity : DummyVelocity_) atIndex:1];
				[Encoder setTexture:Frame.Color atIndex:2];
				[Encoder setTexture:Frame.Output atIndex:3];
				[Encoder setBytes:&Params length:sizeof(Params) atIndex:0];
				[Encoder dispatchThreads:MTLSizeMake(OutputW_, OutputH_, 1) threadsPerThreadgroup:MTLSizeMake(16, 16, 1)];
				[Encoder endEncoding];
			}

			GInFlight.fetch_add(1);
			std::shared_ptr<FScaler> Keep = shared_from_this();
			std::shared_ptr<const FFrameInput> KeepFrame = FramePtr;   // the block owns the retained textures until the GPU is done with them
			[CommandBuffer addCompletedHandler:^(id<MTLCommandBuffer> Done)
			{
				if (Done.status == MTLCommandBufferStatusError)
				{
					Keep->Fail("the MetalFX command buffer failed: " + Str(Done.error.localizedDescription));
					std::lock_guard<std::mutex> Lock(Keep->Mutex_);
					++Keep->Timings_.Errors;
				}
				else
				{
					const float Ms = (float)((Done.GPUEndTime - Done.GPUStartTime) * 1000.0);
					std::lock_guard<std::mutex> Lock(Keep->Mutex_);
					Keep->Timings_.LastMs = Ms;
					Keep->Timings_.AverageMs = Keep->Timings_.Frames == 0 ? Ms : Keep->Timings_.AverageMs * 0.95f + Ms * 0.05f;
					++Keep->Timings_.Frames;
				}
				(void)KeepFrame;
				GInFlight.fetch_sub(1);
			}];
			[CommandBuffer commit];
		}
	}
}
}
