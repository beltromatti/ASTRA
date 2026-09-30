// GPU cost of MTLFXTemporalScaler at the game's sizes on this machine, plus what formats/content sizes it accepts.
// Usage: probe_cost [frames]   (default 200). Set MTL_DEBUG_LAYER=1 to see Metal validation messages.
#include "probe_common.h"

static const char* kSrc = R"MSL(
#include <metal_stdlib>
using namespace metal;
struct SceneParams { float2 Jitter; float2 Cam; float InvScale; uint W; uint H; float Pad; };

float Line(float d, float sigma) { return exp(-0.5 * d * d / (sigma * sigma)); }

// A band-limited-ish world signal in output-pixel units: soft checker, thin lines, rings.
float Signal(float2 p)
{
	float2 c = p * (1.0 / 37.0);
	float checker = 0.5 + 0.5 * sin(c.x * 6.2831853) * sin(c.y * 6.2831853);
	float l1 = Line(fmod(p.x, 23.0) - 11.5, 0.9);
	float l2 = Line(fmod(p.y + 0.37 * p.x, 29.0) - 14.5, 0.9);
	float2 q = p - float2(400.0, 300.0);
	float ring = Line(fmod(length(q), 17.0) - 8.5, 0.8);
	return clamp(0.15 + 0.35 * checker + 0.6 * l1 + 0.6 * l2 + 0.5 * ring, 0.0, 1.5);
}

kernel void synth_color(texture2d<half, access::write> Out [[texture(0)]], constant SceneParams& P [[buffer(0)]], uint2 gid [[thread_position_in_grid]])
{
	if (gid.x >= P.W || gid.y >= P.H) return;
	float2 pin = float2(gid) + 0.5 - P.Jitter;
	float2 world = pin * P.InvScale + P.Cam;
	float v = Signal(world);
	Out.write(half4(half(v), half(v * 0.8), half(v * 0.6), 1.0h), gid);
}

kernel void synth_motion(texture2d<half, access::write> Out [[texture(0)]], constant float2& Mv [[buffer(0)]], uint2 gid [[thread_position_in_grid]])
{
	if (gid.x >= Out.get_width() || gid.y >= Out.get_height()) return;
	Out.write(half4(half(Mv.x), half(Mv.y), 0.0h, 0.0h), gid);
}

kernel void synth_exposure(texture2d<half, access::write> Out [[texture(0)]], constant float& E [[buffer(0)]], uint2 gid [[thread_position_in_grid]])
{
	Out.write(half4(half(E), 0.0h, 0.0h, 0.0h), gid);
}
)MSL";

struct SceneParams { float Jitter[2]; float Cam[2]; float InvScale; uint32_t W; uint32_t H; float Pad; };

static float Halton(int Index, int Base)
{
	float F = 1.0f, R = 0.0f;
	while (Index > 0) { F /= (float)Base; R += F * (float)(Index % Base); Index /= Base; }
	return R;
}

struct FCase
{
	int ExtentW, ExtentH;   // descriptor input size (texture size)
	int ContentW, ContentH; // actual rendered region
	int OutW, OutH;
	bool bDynamic;
	bool bAutoExposure;
	const char* Label;
};

static void RunCase(id<MTLDevice> Dev, id<MTLCommandQueue> Q, id<MTLLibrary> Lib, const FCase& C, int Frames)
{
	id<MTLFXTemporalScaler> S = MakeScaler(Dev, C.ExtentW, C.ExtentH, C.OutW, C.OutH, true, C.bDynamic,
		MTLPixelFormatRGBA16Float, MTLPixelFormatDepth32Float, MTLPixelFormatRG16Float, MTLPixelFormatRGBA16Float, C.bAutoExposure);
	if (!S) { printf("%-44s : scaler creation failed\n", C.Label); return; }
	id<MTLTexture> Color = MakeTex2D(Dev, MTLPixelFormatRGBA16Float, C.ExtentW, C.ExtentH, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite);
	id<MTLTexture> Depth = MakeTex2D(Dev, MTLPixelFormatDepth32Float, C.ExtentW, C.ExtentH, MTLTextureUsageShaderRead | MTLTextureUsageRenderTarget);
	id<MTLTexture> Motion = MakeTex2D(Dev, MTLPixelFormatRG16Float, C.ExtentW, C.ExtentH, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite);
	id<MTLTexture> Out = MakeTex2D(Dev, MTLPixelFormatRGBA16Float, C.OutW, C.OutH, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite | MTLTextureUsageRenderTarget);
	id<MTLTexture> Expo = MakeTex2D(Dev, MTLPixelFormatR16Float, 1, 1, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite);
	id<MTLComputePipelineState> PsoColor = MakePSO(Dev, Lib, "synth_color");
	id<MTLComputePipelineState> PsoMotion = MakePSO(Dev, Lib, "synth_motion");
	id<MTLComputePipelineState> PsoExpo = MakePSO(Dev, Lib, "synth_exposure");

	float Scale = (float)C.ContentW / (float)C.OutW;
	// Static inputs (motion, depth, exposure): written once.
	RunCB(Q, ^(id<MTLCommandBuffer> CB) {
		ClearDepth(CB, Depth, 0.5);
		id<MTLComputeCommandEncoder> E = [CB computeCommandEncoder];
		float Mv[2] = { 0.0f, 0.0f };
		[E setComputePipelineState:PsoMotion]; [E setTexture:Motion atIndex:0]; [E setBytes:Mv length:8 atIndex:0];
		Dispatch2D(E, PsoMotion, C.ExtentW, C.ExtentH);
		float Ex = 1.0f;
		[E setComputePipelineState:PsoExpo]; [E setTexture:Expo atIndex:0]; [E setBytes:&Ex length:4 atIndex:0];
		[E dispatchThreadgroups:MTLSizeMake(1, 1, 1) threadsPerThreadgroup:MTLSizeMake(1, 1, 1)];
		[E endEncoding];
	});

	S.colorTexture = Color; S.depthTexture = Depth; S.motionTexture = Motion; S.outputTexture = Out;
	if (!C.bAutoExposure) S.exposureTexture = Expo;
	S.inputContentWidth = C.ContentW; S.inputContentHeight = C.ContentH;
	S.motionVectorScaleX = 1.0f; S.motionVectorScaleY = 1.0f;
	S.depthReversed = YES;
	S.preExposure = 1.0f;

	// Per-frame: synth color (separate CB, not counted), then the scaler alone in its own CB (counted).
	FStats GpuMs, SynthMs;
	int Warm = 40;
	for (int F = 0; F < Frames + Warm; ++F)
	{
		SceneParams P;
		P.Jitter[0] = Halton(F % 16 + 1, 2) - 0.5f; P.Jitter[1] = Halton(F % 16 + 1, 3) - 0.5f;
		P.Cam[0] = 0.5f * (float)F; P.Cam[1] = 0.0f; P.InvScale = 1.0f / Scale; P.W = C.ContentW; P.H = C.ContentH; P.Pad = 0;
		double T0 = RunCB(Q, ^(id<MTLCommandBuffer> CB) {
			id<MTLComputeCommandEncoder> E = [CB computeCommandEncoder];
			[E setComputePipelineState:PsoColor]; [E setTexture:Color atIndex:0]; [E setBytes:&P length:sizeof P atIndex:0];
			Dispatch2D(E, PsoColor, C.ContentW, C.ContentH);
			[E endEncoding];
		});
		S.jitterOffsetX = P.Jitter[0]; S.jitterOffsetY = P.Jitter[1];
		S.reset = (F == 0);
		double T1 = RunCB(Q, ^(id<MTLCommandBuffer> CB) { [S encodeToCommandBuffer:CB]; });
		if (F >= Warm) { GpuMs.Add(T1); SynthMs.Add(T0); }
	}

	// Steady-state throughput: N scaler CBs back to back, wall time / N, repeated in rounds (the GPU may be shared
	// with other processes, so the minimum over the rounds is the closest to the uncontended cost).
	int N = 60, Rounds = 9;
	FStats RoundMs, EncodeUs;
	for (int R = 0; R < Rounds; ++R)
	{
		double W0 = NowMs();
		id<MTLCommandBuffer> Last = nil;
		for (int F = 0; F < N; ++F)
		{
			id<MTLCommandBuffer> CB = [Q commandBuffer];
			S.jitterOffsetX = Halton(F % 16 + 1, 2) - 0.5f; S.jitterOffsetY = Halton(F % 16 + 1, 3) - 0.5f;
			S.reset = NO;
			double E0 = NowMs();
			[S encodeToCommandBuffer:CB];
			EncodeUs.Add((NowMs() - E0) * 1000.0);
			[CB commit];
			Last = CB;
		}
		[Last waitUntilCompleted];
		RoundMs.Add((NowMs() - W0) / N);
	}

	// Pure scaler time with the GPU kept busy: N scaler runs inside ONE command buffer (they serialise on the history), GPU time / N.
	FStats InCb;
	for (int R = 0; R < 9; ++R)
	{
		const int Inner = 30;
		double Ms = RunCB(Q, ^(id<MTLCommandBuffer> CB) {
			for (int k = 0; k < Inner; ++k) { S.jitterOffsetX = Halton(k % 16 + 1, 2) - 0.5f; S.jitterOffsetY = Halton(k % 16 + 1, 3) - 0.5f; S.reset = NO; [S encodeToCommandBuffer:CB]; }
		});
		InCb.Add(Ms / Inner);
	}
	printf("%-44s : in one CB min %.3f med %.3f ms | back-to-back CBs min %.3f med %.3f | single CB gpu min %.3f | encode cpu %.0f us\n",
		C.Label, InCb.Percentile(0.0), InCb.Median(), RoundMs.Percentile(0.0), RoundMs.Median(), GpuMs.Percentile(0.0), EncodeUs.Median());
}

int main(int argc, char** argv)
{
	int Frames = argc > 1 ? atoi(argv[1]) : 200;
	@autoreleasepool
	{
		id<MTLDevice> Dev = MTLCreateSystemDefaultDevice();
		id<MTLCommandQueue> Q = [Dev newCommandQueue];
		id<MTLLibrary> Lib = MakeLib(Dev, kSrc);
		printf("device %s, %d frames per case\n", Dev.name.UTF8String, Frames);
		// Warm the framework once so creation/compile cost does not pollute the first case.
		{ id<MTLFXTemporalScaler> W = MakeScaler(Dev, 960, 540, 1600, 900, true, false); (void)W; }

		FCase Cases[] = {
			{ 960, 540, 960, 540, 1600, 900, false, false, "960x540  -> 1600x900   (60%)" },
			{ 1120, 630, 1120, 630, 1600, 900, false, false, "1120x630 -> 1600x900   (70%)" },
			{ 1600, 900, 1600, 900, 1600, 900, false, false, "1600x900 -> 1600x900   (100%, TAA-like)" },
			{ 855, 554, 855, 554, 1710, 1107, false, false, "855x554  -> 1710x1107  (50%)" },
			{ 940, 609, 940, 609, 1710, 1107, false, false, "940x609  -> 1710x1107  (55%)" },
			{ 1197, 775, 1197, 775, 1710, 1107, false, false, "1197x775 -> 1710x1107  (70%)" },
			// The UE way: textures allocated at the dynamic-resolution upper bound, content is a corner of them.
			{ 1600, 900, 960, 540, 1600, 900, true, false, "dyn: extent 1600x900, content 960x540" },
			{ 1600, 900, 1120, 630, 1600, 900, true, false, "dyn: extent 1600x900, content 1120x630" },
			{ 1712, 1112, 940, 609, 1710, 1107, true, false, "dyn: extent 1712x1112, content 940x609" },
			{ 1712, 1112, 1197, 775, 1710, 1107, true, false, "dyn: extent 1712x1112, content 1197x775" },
			{ 1120, 630, 1120, 630, 1600, 900, false, true, "1120x630 -> 1600x900 with auto exposure" },
		};
		for (auto& C : Cases) RunCase(Dev, Q, Lib, C, Frames);
	}
	return 0;
}
