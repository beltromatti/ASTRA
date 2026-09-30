// Which conventions does MTLFXTemporalScaler use for the jitter and the motion vectors?
// Renders a synthetic, analytically known scene at low resolution with UE-style sub-pixel jitter and a camera pan,
// runs the scaler for a number of frames and compares the last output with the ground truth (PSNR), for every sign
// combination. The winner tells how UE's TemporalJitterPixels and velocity must be fed to the scaler.
// Usage: probe_quality [frames] [scale_percent]
#include "probe_common.h"
#include <simd/simd.h>

static const char* kSrc = R"MSL(
#include <metal_stdlib>
using namespace metal;
struct SceneParams { float2 Jitter; float2 Cam; float InvScale; uint W; uint H; float Pad; };

float Line(float d, float sigma) { return exp(-0.5 * d * d / (sigma * sigma)); }
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
	Out.write(half4(half(v), half(v), half(v), 1.0h), gid);
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

// CPU replica of the MSL Signal().
static float Line(float d, float sigma) { return expf(-0.5f * d * d / (sigma * sigma)); }
static float Signal(float px, float py)
{
	float cx = px * (1.0f / 37.0f), cy = py * (1.0f / 37.0f);
	float checker = 0.5f + 0.5f * sinf(cx * 6.2831853f) * sinf(cy * 6.2831853f);
	float l1 = Line(fmodf(px, 23.0f) - 11.5f, 0.9f);
	float l2 = Line(fmodf(py + 0.37f * px, 29.0f) - 14.5f, 0.9f);
	float qx = px - 400.0f, qy = py - 300.0f;
	float ring = Line(fmodf(sqrtf(qx * qx + qy * qy), 17.0f) - 8.5f, 0.8f);
	float v = 0.15f + 0.35f * checker + 0.6f * l1 + 0.6f * l2 + 0.5f * ring;
	return std::min(std::max(v, 0.0f), 1.5f);
}

struct FResult { double Psnr; };

static void ReadBack(id<MTLDevice> Dev, id<MTLCommandQueue> Q, id<MTLTexture> Src, int W, int H, std::vector<float>& OutR)
{
	id<MTLTexture> Shared = MakeTex2D(Dev, MTLPixelFormatRGBA16Float, W, H, MTLTextureUsageShaderRead, MTLStorageModeShared);
	RunCB(Q, ^(id<MTLCommandBuffer> CB) {
		id<MTLBlitCommandEncoder> B = [CB blitCommandEncoder];
		[B copyFromTexture:Src toTexture:Shared];
		[B endEncoding];
	});
	std::vector<_Float16> Raw((size_t)W * H * 4);
	[Shared getBytes:Raw.data() bytesPerRow:(size_t)W * 8 fromRegion:MTLRegionMake2D(0, 0, W, H) mipmapLevel:0];
	OutR.resize((size_t)W * H);
	for (size_t i = 0; i < (size_t)W * H; ++i) OutR[i] = (float)Raw[i * 4];
}

int main(int argc, char** argv)
{
	int Frames = argc > 1 ? atoi(argv[1]) : 40;
	int ScalePct = argc > 2 ? atoi(argv[2]) : 60;
	const int OutW = 960, OutH = 540; // smaller output keeps the CPU ground truth cheap
	int InW = (OutW * ScalePct + 50) / 100, InH = (OutH * ScalePct + 50) / 100;
	float Scale = (float)InW / (float)OutW;
	@autoreleasepool
	{
		id<MTLDevice> Dev = MTLCreateSystemDefaultDevice();
		id<MTLCommandQueue> Q = [Dev newCommandQueue];
		id<MTLLibrary> Lib = MakeLib(Dev, kSrc);
		id<MTLComputePipelineState> PsoColor = MakePSO(Dev, Lib, "synth_color");
		id<MTLComputePipelineState> PsoMotion = MakePSO(Dev, Lib, "synth_motion");
		id<MTLComputePipelineState> PsoExpo = MakePSO(Dev, Lib, "synth_exposure");
		printf("input %dx%d -> output %dx%d (scale %.3f), %d frames, pan (0.5, 0.25) output px/frame\n", InW, InH, OutW, OutH, Scale, Frames);

		const float PanX = 0.5f, PanY = 0.25f;
		// Ground truth for the last frame.
		float CamX = PanX * (float)(Frames - 1), CamY = PanY * (float)(Frames - 1);
		std::vector<float> GT((size_t)OutW * OutH);
		for (int y = 0; y < OutH; ++y)
			for (int x = 0; x < OutW; ++x)
			{
				float Acc = 0;
				for (int sy = 0; sy < 4; ++sy)
					for (int sx = 0; sx < 4; ++sx)
						Acc += Signal((float)x + (sx + 0.5f) / 4.0f + CamX, (float)y + (sy + 0.5f) / 4.0f + CamY);
				GT[(size_t)y * OutW + x] = Acc / 16.0f;
			}


		if (argc > 3 && strcmp(argv[3], "layout") == 0)
		{
			// Texture/descriptor layout variants with the correct conventions: does a scaler fed with textures bigger than the
			// content (UE allocates the scene textures at the upper bound of the dynamic resolution) produce the same image?
			struct FLayout { int DescW, DescH, TexW, TexH; bool bDyn; const char* Label; };
			int Ew = OutW * 12 / 10, Eh = OutH * 12 / 10; // pretend the scene textures are 20% bigger than the output
			FLayout Layouts[] = {
				{ InW, InH, InW, InH, false, "desc = content, textures = content (baseline)" },
				{ InW, InH, InW, InH, true, "dyn, desc = content, textures = content" },
				{ OutW, OutH, OutW, OutH, true, "dyn, desc = output size, textures = output size" },
				{ Ew, Eh, Ew, Eh, true, "dyn, desc = extent (1.2x out), textures = extent" },
				{ OutW, OutH, Ew, Eh, true, "dyn, desc = output size, textures = extent (bigger)" },
				{ InW, InH, Ew, Eh, true, "dyn, desc = content, textures = extent (bigger)" },
			};
			for (auto& L : Layouts)
			{
				id<MTLFXTemporalScaler> S = MakeScaler(Dev, L.DescW, L.DescH, OutW, OutH, true, L.bDyn);
				id<MTLTexture> Color = MakeTex2D(Dev, MTLPixelFormatRGBA16Float, L.TexW, L.TexH, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite);
				id<MTLTexture> Depth = MakeTex2D(Dev, MTLPixelFormatDepth32Float, L.TexW, L.TexH, MTLTextureUsageShaderRead | MTLTextureUsageRenderTarget);
				id<MTLTexture> Motion = MakeTex2D(Dev, MTLPixelFormatRG16Float, L.TexW, L.TexH, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite);
				id<MTLTexture> Out = MakeTex2D(Dev, MTLPixelFormatRGBA16Float, OutW, OutH, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite | MTLTextureUsageRenderTarget);
				id<MTLTexture> Expo = MakeTex2D(Dev, MTLPixelFormatR16Float, 1, 1, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite);
				simd_float2 Mv = { PanX * Scale, PanY * Scale };
				int TW = L.TexW, TH = L.TexH;
				RunCB(Q, ^(id<MTLCommandBuffer> CB) {
					ClearDepth(CB, Depth, 0.5);
					id<MTLComputeCommandEncoder> E = [CB computeCommandEncoder];
					[E setComputePipelineState:PsoMotion]; [E setTexture:Motion atIndex:0]; [E setBytes:&Mv length:8 atIndex:0];
					Dispatch2D(E, PsoMotion, TW, TH);
					float Ex = 1.0f;
					[E setComputePipelineState:PsoExpo]; [E setTexture:Expo atIndex:0]; [E setBytes:&Ex length:4 atIndex:0];
					[E dispatchThreadgroups:MTLSizeMake(1, 1, 1) threadsPerThreadgroup:MTLSizeMake(1, 1, 1)];
					[E endEncoding];
				});
				S.colorTexture = Color; S.depthTexture = Depth; S.motionTexture = Motion; S.outputTexture = Out; S.exposureTexture = Expo;
				S.inputContentWidth = InW; S.inputContentHeight = InH;
				S.motionVectorScaleX = 1.0f; S.motionVectorScaleY = 1.0f; S.depthReversed = YES; S.preExposure = 1.0f;
				for (int F = 0; F < Frames; ++F)
				{
					SceneParams P;
					float Dx = Halton(F % 8 + 1, 2) - 0.5f, Dy = Halton(F % 8 + 1, 3) - 0.5f;
					P.Jitter[0] = Dx; P.Jitter[1] = Dy;
					P.Cam[0] = PanX * (float)F; P.Cam[1] = PanY * (float)F; P.InvScale = 1.0f / Scale; P.W = InW; P.H = InH; P.Pad = 0;
					RunCB(Q, ^(id<MTLCommandBuffer> CB) {
						id<MTLComputeCommandEncoder> E = [CB computeCommandEncoder];
						[E setComputePipelineState:PsoColor]; [E setTexture:Color atIndex:0]; [E setBytes:&P length:sizeof P atIndex:0];
						Dispatch2D(E, PsoColor, InW, InH); // only the content rectangle is rendered
						[E endEncoding];
					});
					S.jitterOffsetX = Dx; S.jitterOffsetY = Dy; S.reset = (F == 0);
					RunCB(Q, ^(id<MTLCommandBuffer> CB) { [S encodeToCommandBuffer:CB]; });
				}
				std::vector<float> R;
				ReadBack(Dev, Q, Out, OutW, OutH, R);
				double Se = 0; size_t Cnt = 0;
				for (int y = 40; y < OutH - 40; ++y)
					for (int x = 40; x < OutW - 40; ++x)
					{
						double D = (double)R[(size_t)y * OutW + x] - (double)GT[(size_t)y * OutW + x];
						Se += D * D; ++Cnt;
					}
				printf("%-58s : PSNR %.2f dB\n", L.Label, 10.0 * log10(1.5 * 1.5 / (Se / (double)Cnt)));
			}
			return 0;
		}

		struct FCombo { float Jx, Jy, Mv; const char* Label; };
		FCombo Combos[] = {
			{ +1, +1, +1, "jitter(+x,+y) motion(+)" }, { +1, +1, -1, "jitter(+x,+y) motion(-)" },
			{ -1, +1, +1, "jitter(-x,+y) motion(+)" }, { -1, +1, -1, "jitter(-x,+y) motion(-)" },
			{ +1, -1, +1, "jitter(+x,-y) motion(+)" }, { +1, -1, -1, "jitter(+x,-y) motion(-)" },
			{ -1, -1, +1, "jitter(-x,-y) motion(+)" }, { -1, -1, -1, "jitter(-x,-y) motion(-)" },
			{ 0, 0, +1, "no jitter offset given   motion(+)" }, { +1, +1, 0, "jitter(+x,+y) zero motion" },
		};
		for (auto& Cmb : Combos)
		{
			id<MTLFXTemporalScaler> S = MakeScaler(Dev, InW, InH, OutW, OutH, true, false);
			id<MTLTexture> Color = MakeTex2D(Dev, MTLPixelFormatRGBA16Float, InW, InH, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite);
			id<MTLTexture> Depth = MakeTex2D(Dev, MTLPixelFormatDepth32Float, InW, InH, MTLTextureUsageShaderRead | MTLTextureUsageRenderTarget);
			id<MTLTexture> Motion = MakeTex2D(Dev, MTLPixelFormatRG16Float, InW, InH, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite);
			id<MTLTexture> Out = MakeTex2D(Dev, MTLPixelFormatRGBA16Float, OutW, OutH, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite | MTLTextureUsageRenderTarget);
			id<MTLTexture> Expo = MakeTex2D(Dev, MTLPixelFormatR16Float, 1, 1, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite);
			// World motion of the static scene under the pan, in input pixels: a world point moves by -Pan*Scale on screen per frame,
			// so "previous minus current" is +Pan*Scale.
			simd_float2 Mv = { Cmb.Mv * PanX * Scale, Cmb.Mv * PanY * Scale };
			RunCB(Q, ^(id<MTLCommandBuffer> CB) {
				ClearDepth(CB, Depth, 0.5);
				id<MTLComputeCommandEncoder> E = [CB computeCommandEncoder];
				[E setComputePipelineState:PsoMotion]; [E setTexture:Motion atIndex:0]; [E setBytes:&Mv length:8 atIndex:0];
				Dispatch2D(E, PsoMotion, InW, InH);
				float Ex = 1.0f;
				[E setComputePipelineState:PsoExpo]; [E setTexture:Expo atIndex:0]; [E setBytes:&Ex length:4 atIndex:0];
				[E dispatchThreadgroups:MTLSizeMake(1, 1, 1) threadsPerThreadgroup:MTLSizeMake(1, 1, 1)];
				[E endEncoding];
			});
			S.colorTexture = Color; S.depthTexture = Depth; S.motionTexture = Motion; S.outputTexture = Out; S.exposureTexture = Expo;
			S.inputContentWidth = InW; S.inputContentHeight = InH;
			S.motionVectorScaleX = 1.0f; S.motionVectorScaleY = 1.0f;
			S.depthReversed = YES; S.preExposure = 1.0f;
			for (int F = 0; F < Frames; ++F)
			{
				SceneParams P;
				float Dx = Halton(F % 8 + 1, 2) - 0.5f, Dy = Halton(F % 8 + 1, 3) - 0.5f; // UE: image shifted by +delta input px
				P.Jitter[0] = Dx; P.Jitter[1] = Dy;
				P.Cam[0] = PanX * (float)F; P.Cam[1] = PanY * (float)F; P.InvScale = 1.0f / Scale; P.W = InW; P.H = InH; P.Pad = 0;
				RunCB(Q, ^(id<MTLCommandBuffer> CB) {
					id<MTLComputeCommandEncoder> E = [CB computeCommandEncoder];
					[E setComputePipelineState:PsoColor]; [E setTexture:Color atIndex:0]; [E setBytes:&P length:sizeof P atIndex:0];
					Dispatch2D(E, PsoColor, InW, InH);
					[E endEncoding];
				});
				S.jitterOffsetX = Cmb.Jx * Dx; S.jitterOffsetY = Cmb.Jy * Dy;
				S.reset = (F == 0);
				RunCB(Q, ^(id<MTLCommandBuffer> CB) { [S encodeToCommandBuffer:CB]; });
			}
			std::vector<float> R;
			ReadBack(Dev, Q, Out, OutW, OutH, R);
			double Se = 0; size_t Cnt = 0;
			for (int y = 40; y < OutH - 40; ++y)
				for (int x = 40; x < OutW - 40; ++x)
				{
					double D = (double)R[(size_t)y * OutW + x] - (double)GT[(size_t)y * OutW + x];
					Se += D * D; ++Cnt;
				}
			double Mse = Se / (double)Cnt;
			printf("%-38s : PSNR %.2f dB\n", Cmb.Label, 10.0 * log10(1.5 * 1.5 / Mse));
		}
	}
	return 0;
}
