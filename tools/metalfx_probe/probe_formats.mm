// Which input/output formats and texture layouts does the scaler accept at encode time? (UE gives it a
// Depth32Float_Stencil8 depth, an RGBA16 UNORM velocity, an RGBA16F color, textures bigger than the content, ...)
// Run with MTL_DEBUG_LAYER=1 and 2>&1 to see the validation messages next to the verdict.
#include "probe_common.h"

static const char* kSrc = R"MSL(
#include <metal_stdlib>
using namespace metal;
kernel void fill_color(texture2d<half, access::write> Out [[texture(0)]], uint2 gid [[thread_position_in_grid]])
{
	if (gid.x >= Out.get_width() || gid.y >= Out.get_height()) return;
	float v = 0.5 + 0.5 * sin(float(gid.x) * 0.1) * sin(float(gid.y) * 0.1);
	Out.write(half4(half(v), half(v), half(v), 1.0h), gid);
}
kernel void fill_motion(texture2d<half, access::write> Out [[texture(0)]], uint2 gid [[thread_position_in_grid]])
{
	if (gid.x >= Out.get_width() || gid.y >= Out.get_height()) return;
	Out.write(half4(0.25h, -0.25h, 0.0h, 0.0h), gid);
}
kernel void fill_motion32(texture2d<float, access::write> Out [[texture(0)]], uint2 gid [[thread_position_in_grid]])
{
	if (gid.x >= Out.get_width() || gid.y >= Out.get_height()) return;
	Out.write(float4(0.25, -0.25, 0.0, 0.0), gid);
}
kernel void fill_r32(texture2d<float, access::write> Out [[texture(0)]], uint2 gid [[thread_position_in_grid]])
{
	if (gid.x >= Out.get_width() || gid.y >= Out.get_height()) return;
	Out.write(float4(0.5, 0, 0, 0), gid);
}
kernel void fill_expo(texture2d<half, access::write> Out [[texture(0)]], uint2 gid [[thread_position_in_grid]])
{
	Out.write(half4(1.0h, 0, 0, 0), gid);
}
)MSL";

static void FillDepthStencil(id<MTLCommandBuffer> CB, id<MTLTexture> Depth, bool bStencil)
{
	MTLRenderPassDescriptor* RP = [MTLRenderPassDescriptor renderPassDescriptor];
	RP.depthAttachment.texture = Depth;
	RP.depthAttachment.loadAction = MTLLoadActionClear;
	RP.depthAttachment.storeAction = MTLStoreActionStore;
	RP.depthAttachment.clearDepth = 0.5;
	if (bStencil)
	{
		RP.stencilAttachment.texture = Depth;
		RP.stencilAttachment.loadAction = MTLLoadActionClear;
		RP.stencilAttachment.storeAction = MTLStoreActionStore;
		RP.stencilAttachment.clearStencil = 0;
	}
	id<MTLRenderCommandEncoder> E = [CB renderCommandEncoderWithDescriptor:RP];
	[E endEncoding];
}

struct FFormatCase
{
	const char* Label;
	MTLPixelFormat Color, Depth, Motion, Out;
	bool bDepthStencilTexture;      // depth texture is a packed depth/stencil target
	bool bDepthViaCompute;          // depth texture is a color format filled by compute
	bool bMotionFloat32;
	int ExtentW, ExtentH, ContentW, ContentH, OutW, OutH;
	bool bDynamic;
	int TexW = 0, TexH = 0;         // actual input textures size when different from the descriptor's (0 = same)
};

static void RunCase(id<MTLDevice> Dev, id<MTLCommandQueue> Q, id<MTLLibrary> Lib, const FFormatCase& C)
{
	id<MTLFXTemporalScaler> S = MakeScaler(Dev, C.ExtentW, C.ExtentH, C.OutW, C.OutH, true, C.bDynamic, C.Color, C.Depth, C.Motion, C.Out);
	if (!S) { printf("%-58s : scaler NOT created\n", C.Label); return; }
	int TW = C.TexW ? C.TexW : C.ExtentW, TH = C.TexH ? C.TexH : C.ExtentH;
	id<MTLTexture> Color = MakeTex2D(Dev, C.Color, TW, TH, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite | MTLTextureUsageRenderTarget);
	MTLTextureUsage DepthUse = MTLTextureUsageShaderRead | (C.bDepthViaCompute ? MTLTextureUsageShaderWrite : MTLTextureUsageRenderTarget);
	id<MTLTexture> Depth = MakeTex2D(Dev, C.Depth, TW, TH, DepthUse);
	id<MTLTexture> Motion = MakeTex2D(Dev, C.Motion, TW, TH, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite);
	id<MTLTexture> Out = MakeTex2D(Dev, C.Out, C.OutW, C.OutH, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite | MTLTextureUsageRenderTarget);
	id<MTLTexture> Expo = MakeTex2D(Dev, MTLPixelFormatR16Float, 1, 1, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite);
	if (!Color || !Depth || !Motion || !Out) { printf("%-58s : texture creation failed\n", C.Label); return; }
	id<MTLComputePipelineState> PsoColor = MakePSO(Dev, Lib, "fill_color");
	id<MTLComputePipelineState> PsoMotion = MakePSO(Dev, Lib, C.bMotionFloat32 ? "fill_motion32" : "fill_motion");
	id<MTLComputePipelineState> PsoR32 = MakePSO(Dev, Lib, "fill_r32");
	id<MTLComputePipelineState> PsoExpo = MakePSO(Dev, Lib, "fill_expo");
	bool bErr = false;
	RunCB(Q, ^(id<MTLCommandBuffer> CB) {
		if (!C.bDepthViaCompute) FillDepthStencil(CB, Depth, C.bDepthStencilTexture);
		id<MTLComputeCommandEncoder> E = [CB computeCommandEncoder];
		[E setComputePipelineState:PsoColor]; [E setTexture:Color atIndex:0]; Dispatch2D(E, PsoColor, TW, TH);
		[E setComputePipelineState:PsoMotion]; [E setTexture:Motion atIndex:0]; Dispatch2D(E, PsoMotion, TW, TH);
		if (C.bDepthViaCompute) { [E setComputePipelineState:PsoR32]; [E setTexture:Depth atIndex:0]; Dispatch2D(E, PsoR32, TW, TH); }
		[E setComputePipelineState:PsoExpo]; [E setTexture:Expo atIndex:0]; [E dispatchThreadgroups:MTLSizeMake(1, 1, 1) threadsPerThreadgroup:MTLSizeMake(1, 1, 1)];
		[E endEncoding];
	}, &bErr);
	S.colorTexture = Color; S.depthTexture = Depth; S.motionTexture = Motion; S.outputTexture = Out; S.exposureTexture = Expo;
	S.inputContentWidth = C.ContentW; S.inputContentHeight = C.ContentH;
	S.motionVectorScaleX = 1.0f; S.motionVectorScaleY = 1.0f; S.depthReversed = YES; S.preExposure = 1.0f;
	for (int F = 0; F < 4; ++F)
	{
		S.reset = (F == 0);
		S.jitterOffsetX = 0.1f * F; S.jitterOffsetY = -0.1f * F;
		RunCB(Q, ^(id<MTLCommandBuffer> CB) { [S encodeToCommandBuffer:CB]; }, &bErr);
	}
	printf("%-58s : %s\n", C.Label, bErr ? "ERROR" : "ok");
}

int main(int argc, char** argv)
{
	@autoreleasepool
	{
		id<MTLDevice> Dev = MTLCreateSystemDefaultDevice();
		id<MTLCommandQueue> Q = [Dev newCommandQueue];
		id<MTLLibrary> Lib = MakeLib(Dev, kSrc);
		MTLPixelFormat F16 = MTLPixelFormatRGBA16Float, D32 = MTLPixelFormatDepth32Float, D32S8 = MTLPixelFormatDepth32Float_Stencil8;
		MTLPixelFormat RG16 = MTLPixelFormatRG16Float, RG32 = MTLPixelFormatRG32Float, RGBA16 = MTLPixelFormatRGBA16Float;
		MTLPixelFormat RGBA16U = MTLPixelFormatRGBA16Unorm, RG16U = MTLPixelFormatRG16Unorm;
		FFormatCase Cases[] = {
			{ "baseline RGBA16F / Depth32F / RG16F", F16, D32, RG16, F16, false, false, false, 1120, 630, 1120, 630, 1600, 900, false },
			{ "depth = Depth32Float_Stencil8 (UE depth)", F16, D32S8, RG16, F16, true, false, false, 1120, 630, 1120, 630, 1600, 900, false },
			{ "depth = R32Float (compute copy)", F16, MTLPixelFormatR32Float, RG16, F16, false, true, false, 1120, 630, 1120, 630, 1600, 900, false },
			{ "depth = R16Float (compute copy)", F16, MTLPixelFormatR16Float, RG16, F16, false, true, false, 1120, 630, 1120, 630, 1600, 900, false },
			{ "motion = RG32Float", F16, D32, RG32, F16, false, false, true, 1120, 630, 1120, 630, 1600, 900, false },
			{ "motion = RGBA16Float", F16, D32, RGBA16, F16, false, false, false, 1120, 630, 1120, 630, 1600, 900, false },
			{ "motion = RGBA16Unorm (raw UE velocity as is)", F16, D32, RGBA16U, F16, false, false, false, 1120, 630, 1120, 630, 1600, 900, false },
			{ "motion = RG16Unorm (raw UE velocity as is)", F16, D32, RG16U, F16, false, false, false, 1120, 630, 1120, 630, 1600, 900, false },
			{ "color = RGB10A2Unorm", MTLPixelFormatRGB10A2Unorm, D32, RG16, F16, false, false, false, 1120, 630, 1120, 630, 1600, 900, false },
			{ "color = RG11B10Float", MTLPixelFormatRG11B10Float, D32, RG16, F16, false, false, false, 1120, 630, 1120, 630, 1600, 900, false },
			{ "color = RGBA16F, out = RG11B10Float", F16, D32, RG16, MTLPixelFormatRG11B10Float, false, false, false, 1120, 630, 1120, 630, 1600, 900, false },
			{ "dyn, extent 1600x900 (UE upper bound), content 1120x630", F16, D32S8, RG16, F16, true, false, false, 1600, 900, 1120, 630, 1600, 900, true },
			{ "dyn, extent 1712x1112 -> out 1710x1107, content 940x609", F16, D32S8, RG16, F16, true, false, false, 1712, 1112, 940, 609, 1710, 1107, true },
			{ "NON dyn, extent 1600x900, content 1120x630 (mismatch)", F16, D32, RG16, F16, false, false, false, 1600, 900, 1120, 630, 1600, 900, false },
			{ "dyn, content at max (1600x900 of 1600x900)", F16, D32, RG16, F16, false, false, false, 1600, 900, 1600, 900, 1600, 900, true },
			{ "dyn, content below min scale (output/3.5)", F16, D32, RG16, F16, false, false, false, 1600, 900, 457, 257, 1600, 900, true },
			{ "dyn, desc input 1600x900, textures 1712x1112 (bigger)", F16, D32S8, RG16, F16, true, false, false, 1600, 900, 940, 609, 1600, 900, true, 1712, 1112 },
			{ "dyn, desc input 1712x1112, textures 1600x900 (smaller)", F16, D32S8, RG16, F16, true, false, false, 1712, 1112, 940, 609, 1600, 900, true, 1600, 900 },
			{ "dyn, desc input 960x540, textures 1712x1112, content 940x609", F16, D32S8, RG16, F16, true, false, false, 960, 540, 940, 609, 1710, 1107, true, 1712, 1112 },
		};
		// Some cases trip a hard MetalFX assertion (abort); run a single case with `probe_formats <index>`.
		int Only = argc > 1 ? atoi(argv[1]) : -1;
		int NumCases = (int)(sizeof(Cases) / sizeof(Cases[0]));
		if (Only < 0) { printf("(cases that abort are skipped; run them with an index)\n"); }
		for (int I = 0; I < NumCases; ++I)
		{
			bool bRisky = I >= 13;
			if (Only >= 0 ? I != Only : bRisky) continue;
			RunCase(Dev, Q, Lib, Cases[I]);
		}
	}
	return 0;
}
