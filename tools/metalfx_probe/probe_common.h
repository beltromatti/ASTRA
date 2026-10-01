// Shared helpers for the standalone MetalFX probes (Objective-C++, ARC).
#pragma once
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <MetalFX/MetalFX.h>
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

static inline double NowMs() { return CFAbsoluteTimeGetCurrent() * 1000.0; }

struct FStats
{
	std::vector<double> V;
	void Add(double X) { V.push_back(X); }
	double Percentile(double P) const
	{
		if (V.empty()) return 0.0;
		std::vector<double> S = V;
		std::sort(S.begin(), S.end());
		size_t I = std::min(S.size() - 1, (size_t)(P * (double)(S.size() - 1) + 0.5));
		return S[I];
	}
	double Median() const { return Percentile(0.5); }
	double Mean() const
	{
		double A = 0; for (double X : V) A += X; return V.empty() ? 0.0 : A / (double)V.size();
	}
};

static inline id<MTLTexture> MakeTex2D(id<MTLDevice> Dev, MTLPixelFormat Fmt, int W, int H, MTLTextureUsage Usage,
	MTLStorageMode Storage = MTLStorageModePrivate, const char* Label = nullptr)
{
	MTLTextureDescriptor* D = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:Fmt width:W height:H mipmapped:NO];
	D.usage = Usage;
	D.storageMode = Storage;
	id<MTLTexture> T = [Dev newTextureWithDescriptor:D];
	if (Label) T.label = [NSString stringWithUTF8String:Label];
	return T;
}

static inline id<MTLComputePipelineState> MakePSO(id<MTLDevice> Dev, id<MTLLibrary> Lib, const char* Fn)
{
	NSError* Err = nil;
	id<MTLFunction> F = [Lib newFunctionWithName:[NSString stringWithUTF8String:Fn]];
	if (!F) { printf("kernel %s not found\n", Fn); exit(1); }
	id<MTLComputePipelineState> P = [Dev newComputePipelineStateWithFunction:F error:&Err];
	if (!P) { printf("PSO %s failed: %s\n", Fn, Err.localizedDescription.UTF8String); exit(1); }
	return P;
}

static inline id<MTLLibrary> MakeLib(id<MTLDevice> Dev, const char* Src)
{
	NSError* Err = nil;
	MTLCompileOptions* O = [MTLCompileOptions new];
	O.fastMathEnabled = YES;
	id<MTLLibrary> L = [Dev newLibraryWithSource:[NSString stringWithUTF8String:Src] options:O error:&Err];
	if (!L) { printf("library compile failed: %s\n", Err.localizedDescription.UTF8String); exit(1); }
	return L;
}

// Runs a command buffer to completion and returns the GPU time in ms (start..end), or -1 on error.
static inline double RunCB(id<MTLCommandQueue> Q, void (^Encode)(id<MTLCommandBuffer>), bool* bErr = nullptr)
{
	id<MTLCommandBuffer> CB = [Q commandBuffer];
	Encode(CB);
	[CB commit];
	[CB waitUntilCompleted];
	if (CB.error)
	{
		printf("command buffer error: %s\n", CB.error.localizedDescription.UTF8String);
		if (bErr) *bErr = true;
		return -1.0;
	}
	return (CB.GPUEndTime - CB.GPUStartTime) * 1000.0;
}

// Fills a Depth32Float texture with a constant using a render pass (depth formats cannot be written from compute).
static inline void ClearDepth(id<MTLCommandBuffer> CB, id<MTLTexture> Depth, double Value)
{
	MTLRenderPassDescriptor* RP = [MTLRenderPassDescriptor renderPassDescriptor];
	RP.depthAttachment.texture = Depth;
	RP.depthAttachment.loadAction = MTLLoadActionClear;
	RP.depthAttachment.storeAction = MTLStoreActionStore;
	RP.depthAttachment.clearDepth = Value;
	id<MTLRenderCommandEncoder> E = [CB renderCommandEncoderWithDescriptor:RP];
	[E endEncoding];
}

static inline void Dispatch2D(id<MTLComputeCommandEncoder> E, id<MTLComputePipelineState> P, int W, int H)
{
	MTLSize Tg = MTLSizeMake(16, 16, 1);
	MTLSize Grid = MTLSizeMake((W + 15) / 16, (H + 15) / 16, 1);
	(void)P;
	[E dispatchThreadgroups:Grid threadsPerThreadgroup:Tg];
}

static inline id<MTLFXTemporalScaler> MakeScaler(id<MTLDevice> Dev, int InW, int InH, int OutW, int OutH, bool bSyncInit,
	bool bDynamic, MTLPixelFormat ColorFmt = MTLPixelFormatRGBA16Float, MTLPixelFormat DepthFmt = MTLPixelFormatDepth32Float,
	MTLPixelFormat MotionFmt = MTLPixelFormatRG16Float, MTLPixelFormat OutFmt = MTLPixelFormatRGBA16Float, bool bAutoExposure = false)
{
	MTLFXTemporalScalerDescriptor* D = [MTLFXTemporalScalerDescriptor new];
	D.colorTextureFormat = ColorFmt;
	D.depthTextureFormat = DepthFmt;
	D.motionTextureFormat = MotionFmt;
	D.outputTextureFormat = OutFmt;
	D.inputWidth = InW; D.inputHeight = InH;
	D.outputWidth = OutW; D.outputHeight = OutH;
	D.autoExposureEnabled = bAutoExposure;
	D.requiresSynchronousInitialization = bSyncInit;
	if (bDynamic)
	{
		D.inputContentPropertiesEnabled = YES;
		D.inputContentMinScale = 1.0f;
		D.inputContentMaxScale = 3.0f;
	}
	return [D newTemporalScalerWithDevice:Dev];
}
