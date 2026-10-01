// How much GPU memory does a MetalFX temporal scaler hold (device.currentAllocatedSize before and after creating it and
// running its first frames), for the sizes of the game. Usage: probe_memory
#include "probe_common.h"

static double Mb(NSUInteger Bytes) { return (double)Bytes / (1024.0 * 1024.0); }

int main()
{
	@autoreleasepool
	{
		id<MTLDevice> Dev = MTLCreateSystemDefaultDevice();
		id<MTLCommandQueue> Q = [Dev newCommandQueue];
		struct FCase { int InW, InH, OutW, OutH; };
		FCase Cases[] = { { 1120, 630, 1600, 900 }, { 1710, 1107, 1710, 1107 }, { 1920, 1080, 1920, 1080 }, { 2560, 1440, 2560, 1440 } };
		{ id<MTLFXTemporalScaler> Warm = MakeScaler(Dev, 960, 540, 1600, 900, true, false); (void)Warm; }
		for (auto& C : Cases)
		{
			NSUInteger Before = Dev.currentAllocatedSize;
			id<MTLFXTemporalScaler> S = MakeScaler(Dev, C.InW, C.InH, C.OutW, C.OutH, true, true);
			NSUInteger AfterCreate = Dev.currentAllocatedSize;
			id<MTLTexture> Color = MakeTex2D(Dev, MTLPixelFormatRGBA16Float, C.InW, C.InH, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite);
			id<MTLTexture> Depth = MakeTex2D(Dev, MTLPixelFormatDepth32Float, C.InW, C.InH, MTLTextureUsageShaderRead | MTLTextureUsageRenderTarget);
			id<MTLTexture> Motion = MakeTex2D(Dev, MTLPixelFormatRG16Float, C.InW, C.InH, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite);
			id<MTLTexture> Out = MakeTex2D(Dev, MTLPixelFormatRGBA16Float, C.OutW, C.OutH, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite | MTLTextureUsageRenderTarget);
			id<MTLTexture> Expo = MakeTex2D(Dev, MTLPixelFormatR16Float, 1, 1, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite);
			NSUInteger WithTextures = Dev.currentAllocatedSize;
			S.colorTexture = Color; S.depthTexture = Depth; S.motionTexture = Motion; S.outputTexture = Out; S.exposureTexture = Expo;
			S.inputContentWidth = C.InW; S.inputContentHeight = C.InH; S.motionVectorScaleX = 1; S.motionVectorScaleY = 1; S.depthReversed = YES;
			for (int F = 0; F < 4; ++F)
			{
				S.reset = (F == 0);
				RunCB(Q, ^(id<MTLCommandBuffer> CB) { ClearDepth(CB, Depth, 0.5); [S encodeToCommandBuffer:CB]; });
			}
			NSUInteger AfterRun = Dev.currentAllocatedSize;
			printf("%dx%d -> %dx%d: scaler %.1f MB at creation, %.1f MB more after its first frames (textures of the test: %.1f MB)\n",
				C.InW, C.InH, C.OutW, C.OutH, Mb(AfterCreate - Before), Mb(AfterRun - WithTextures), Mb(WithTextures - AfterCreate));
			S = nil; Color = Depth = Motion = Out = Expo = nil;
		}
	}
	return 0;
}
