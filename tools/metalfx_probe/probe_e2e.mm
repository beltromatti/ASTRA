// End to end: a 3D scene (textured floor + wall) seen by a camera that moves and turns, rendered at low resolution with
// Unreal-style sub-pixel jitter and a reverse-Z depth, upscaled by MetalFX using the motion vectors that the plugin's
// own kernel derives from the depth and ClipToPrevClip, compared with a supersampled ground truth at the output
// resolution. Variants show that the motion matters (zero / negated motion are worse) and what a plain bilinear upscale of
// one frame gives. Usage: probe_e2e [frames] [scale_percent]
#include "probe_common.h"
#include "probe_math.h"
#include "../../Plugins/AstraMetalFX/Source/AstraMetalFX/Private/AstraMetalFXKernels.inl"

static const char* kSrcScene = R"MSL(
#include <metal_stdlib>
using namespace metal;
struct E2EParams { float4 Pos; float4 Right; float4 Up; float4 Fwd; float2 Tan; float2 Jitter; uint2 Size; uint SS; float MinZ; };

float Line(float d, float sigma) { return exp(-0.5 * d * d / (sigma * sigma)); }
float Sig(float2 p)
{
	float2 c = p * (1.0 / 41.0);
	float checker = 0.5 + 0.5 * sin(c.x * 6.2831853) * sin(c.y * 6.2831853);
	float l1 = Line(fmod(fabs(p.x), 9.0) - 4.5, 0.55);
	float l2 = Line(fmod(fabs(p.y + 0.37 * p.x), 13.0) - 6.5, 0.55);
	float2 q = p - float2(500.0, 100.0);
	float ring = Line(fmod(length(q), 17.0) - 8.5, 0.6);
	return clamp(0.15 + 0.35 * checker + 0.55 * l1 + 0.55 * l2 + 0.45 * ring, 0.0, 1.5);
}

// Returns linear colour, writes device depth (reverse Z, infinite far) of the nearest hit.
float4 Shade(constant E2EParams& P, float2 S, thread float& DeviceZ)
{
	float3 Dir = P.Fwd.xyz + P.Right.xyz * (S.x * P.Tan.x) + P.Up.xyz * (S.y * P.Tan.y);
	float T = 1e30;
	bool bFloor = false;
	if (Dir.z < -1e-6) { T = (0.0 - P.Pos.z) / Dir.z; bFloor = true; }
	if (Dir.x > 1e-6) { float Tw = (900.0 - P.Pos.x) / Dir.x; if (Tw < T) { T = Tw; bFloor = false; } }
	if (T > 1e29) { DeviceZ = 0.0; return float4(0.05, 0.08, 0.15, 1.0); }
	float3 Hit = P.Pos.xyz + Dir * T;
	float Zv = dot(Hit - P.Pos.xyz, P.Fwd.xyz);
	DeviceZ = P.MinZ / Zv;
	float V = bFloor ? Sig(Hit.xy) : Sig(Hit.yz + float2(17.0, 3.0));
	return bFloor ? float4(V, V * 0.85, V * 0.7, 1.0) : float4(V * 0.7, V * 0.85, V, 1.0);
}

kernel void e2e_render(texture2d<half, access::write> Color [[texture(0)]], texture2d<float, access::write> Depth [[texture(1)]],
	constant E2EParams& P [[buffer(0)]], uint2 gid [[thread_position_in_grid]])
{
	if (any(gid >= P.Size)) return;
	float4 Acc = float4(0.0); float Z = 0.0;
	for (uint sy = 0; sy < P.SS; ++sy)
		for (uint sx = 0; sx < P.SS; ++sx)
		{
			// Unreal's jitter: the image is shifted by +Jitter pixels, i.e. the sample sits at (pixel centre - Jitter).
			float2 Px = float2(gid) + (float2(sx, sy) + 0.5) / float(P.SS) - P.Jitter;
			float2 S = float2(Px.x / float(P.Size.x) * 2.0 - 1.0, 1.0 - Px.y / float(P.Size.y) * 2.0);
			float DZ; Acc += Shade(P, S, DZ); if (sx == P.SS / 2 && sy == P.SS / 2) Z = DZ;
		}
	Acc /= float(P.SS * P.SS);
	Color.write(half4(half3(Acc.rgb), 1.0h), gid);
	Depth.write(float4(Z, 0, 0, 0), gid);
}

kernel void e2e_zero_velocity(texture2d<float, access::write> Out [[texture(0)]], uint2 gid [[thread_position_in_grid]])
{
	if (gid.x >= Out.get_width() || gid.y >= Out.get_height()) return;
	Out.write(float4(0.0), gid);
}

kernel void e2e_negate(texture2d<half, access::read> In [[texture(0)]], texture2d<half, access::write> Out [[texture(1)]], uint2 gid [[thread_position_in_grid]])
{
	if (gid.x >= Out.get_width() || gid.y >= Out.get_height()) return;
	half4 V = In.read(gid); Out.write(half4(-V.x, -V.y, 0, 0), gid);
}
kernel void e2e_zero_motion(texture2d<half, access::write> Out [[texture(0)]], uint2 gid [[thread_position_in_grid]])
{
	if (gid.x >= Out.get_width() || gid.y >= Out.get_height()) return;
	Out.write(half4(0), gid);
}

kernel void e2e_bilinear(texture2d<half, access::sample> In [[texture(0)]], texture2d<half, access::write> Out [[texture(1)]], constant float2& ContentUV [[buffer(0)]], uint2 gid [[thread_position_in_grid]])
{
	if (gid.x >= Out.get_width() || gid.y >= Out.get_height()) return;
	constexpr sampler S(filter::linear, address::clamp_to_edge);
	float2 UV = (float2(gid) + 0.5) / float2(Out.get_width(), Out.get_height());
	Out.write(In.sample(S, UV * ContentUV), gid);
}
)MSL";

struct E2EParams { float Pos[4], Right[4], Up[4], Fwd[4]; float Tan[2], Jitter[2]; uint32_t Size[2]; uint32_t SS; float MinZ; };
struct FParams { float ClipToPrevClip[16]; uint32_t ViewRectMin[2], ViewSize[2], VelocityExtent[2]; float ScreenToPixel[2]; float ExposureFallback; uint32_t Flags, DebugMode, Pad; };

static float Halton(int Index, int Base)
{
	float F = 1.0f, R = 0.0f;
	while (Index > 0) { F /= (float)Base; R += F * (float)(Index % Base); Index /= Base; }
	return R;
}

static Camera CameraAt(int F)
{
	Camera C;
	C.Pos[0] = 100.0 + 1.1 * F; C.Pos[1] = 40.0 + 0.6 * F + 6.0 * sin(F * 0.07); C.Pos[2] = 170.0 + 0.05 * F;
	C.Yaw = 0.30 + 0.0030 * F; C.Pitch = -0.05 + 0.0015 * F + 0.01 * sin(F * 0.05);
	return C;
}

static E2EParams MakeScene(const Camera& C, int W, int H, double HalfFov, float MinZ, float Jx, float Jy, int SS)
{
	double cy = cos(C.Yaw), sy = sin(C.Yaw), cp = cos(C.Pitch), sp = sin(C.Pitch);
	E2EParams P{};
	double Fwd[3] = { cp * cy, cp * sy, sp }, Right[3] = { -sy, cy, 0 }, Up[3] = { -sp * cy, -sp * sy, cp };
	for (int i = 0; i < 3; ++i) { P.Pos[i] = (float)C.Pos[i]; P.Right[i] = (float)Right[i]; P.Up[i] = (float)Up[i]; P.Fwd[i] = (float)Fwd[i]; }
	P.Tan[0] = (float)tan(HalfFov); P.Tan[1] = (float)(tan(HalfFov) * (double)H / W);
	P.Jitter[0] = Jx; P.Jitter[1] = Jy; P.Size[0] = W; P.Size[1] = H; P.SS = SS; P.MinZ = MinZ;
	return P;
}

int main(int argc, char** argv)
{
	int Frames = argc > 1 ? atoi(argv[1]) : 48;
	int ScalePct = argc > 2 ? atoi(argv[2]) : 55;
	const int OutW = 960, OutH = 540;
	const int InW = (OutW * ScalePct + 50) / 100, InH = (OutH * ScalePct + 50) / 100;
	const double HalfFov = 45.0 * M_PI / 180.0; const float MinZ = 5.0f;
	@autoreleasepool
	{
		id<MTLDevice> Dev = MTLCreateSystemDefaultDevice();
		id<MTLCommandQueue> Q = [Dev newCommandQueue];
		id<MTLLibrary> Lib = MakeLib(Dev, kSrcScene), KLib = MakeLib(Dev, kAstraMetalFXKernelSource);
		id<MTLComputePipelineState> PsoRender = MakePSO(Dev, Lib, "e2e_render"), PsoZeroVel = MakePSO(Dev, Lib, "e2e_zero_velocity"),
			PsoNeg = MakePSO(Dev, Lib, "e2e_negate"), PsoZeroMot = MakePSO(Dev, Lib, "e2e_zero_motion"), PsoBil = MakePSO(Dev, Lib, "e2e_bilinear"),
			PsoMotion = MakePSO(Dev, KLib, "astra_motion"), PsoExpo = MakePSO(Dev, KLib, "astra_exposure");

		// Depth goes through a Depth32Float_Stencil8 target, as in Unreal.
		id<MTLLibrary> RLib = MakeLib(Dev, R"MSL(
#include <metal_stdlib>
using namespace metal;
struct VOut { float4 Pos [[position]]; };
vertex VOut fs_vs(uint Vid [[vertex_id]]) { float2 P = float2(float((Vid << 1) & 2), float(Vid & 2)); VOut O; O.Pos = float4(P * 2.0 - 1.0, 0.0, 1.0); return O; }
struct FOut { float Depth [[depth(any)]]; };
fragment FOut fs_depth(VOut In [[stage_in]], texture2d<float, access::read> Src [[texture(0)]]) { FOut O; O.Depth = Src.read(uint2(In.Pos.xy)).x; return O; }
)MSL");
		MTLRenderPipelineDescriptor* RPD = [MTLRenderPipelineDescriptor new];
		RPD.vertexFunction = [RLib newFunctionWithName:@"fs_vs"]; RPD.fragmentFunction = [RLib newFunctionWithName:@"fs_depth"];
		RPD.depthAttachmentPixelFormat = MTLPixelFormatDepth32Float_Stencil8; RPD.stencilAttachmentPixelFormat = MTLPixelFormatDepth32Float_Stencil8;
		NSError* Err = nil;
		id<MTLRenderPipelineState> RPS = [Dev newRenderPipelineStateWithDescriptor:RPD error:&Err];
		MTLDepthStencilDescriptor* DSD = [MTLDepthStencilDescriptor new]; DSD.depthCompareFunction = MTLCompareFunctionAlways; DSD.depthWriteEnabled = YES;
		id<MTLDepthStencilState> DSS = [Dev newDepthStencilStateWithDescriptor:DSD];

		id<MTLTexture> Color = MakeTex2D(Dev, MTLPixelFormatRGBA16Float, InW, InH, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite);
		id<MTLTexture> DepthR32 = MakeTex2D(Dev, MTLPixelFormatR32Float, InW, InH, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite);
		id<MTLTexture> Depth = MakeTex2D(Dev, MTLPixelFormatDepth32Float_Stencil8, InW, InH, MTLTextureUsageShaderRead | MTLTextureUsageRenderTarget);
		id<MTLTexture> Vel = MakeTex2D(Dev, MTLPixelFormatRGBA16Unorm, InW, InH, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite);
		id<MTLTexture> MotionKernel = MakeTex2D(Dev, MTLPixelFormatRG16Float, InW, InH, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite);
		id<MTLTexture> MotionNeg = MakeTex2D(Dev, MTLPixelFormatRG16Float, InW, InH, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite);
		id<MTLTexture> MotionZero = MakeTex2D(Dev, MTLPixelFormatRG16Float, InW, InH, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite);
		id<MTLTexture> Expo = MakeTex2D(Dev, MTLPixelFormatR16Float, 1, 1, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite);
		id<MTLTexture> Eye = MakeTex2D(Dev, MTLPixelFormatRGBA32Float, 1, 1, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite);

		struct FVariant { const char* Label; id<MTLTexture> Motion; id<MTLFXTemporalScaler> S; id<MTLTexture> Out; };
		std::vector<FVariant> V;
		id<MTLTexture> Motions[3] = { MotionKernel, MotionZero, MotionNeg };
		const char* Labels[3] = { "MetalFX with the plugin's motion kernel", "MetalFX with zero motion", "MetalFX with negated motion" };
		for (int i = 0; i < 3; ++i)
		{
			FVariant X;
			X.Label = Labels[i]; X.Motion = Motions[i];
			X.S = MakeScaler(Dev, OutW, OutH, OutW, OutH, true, true, MTLPixelFormatRGBA16Float, MTLPixelFormatDepth32Float_Stencil8);
			X.Out = MakeTex2D(Dev, MTLPixelFormatRGBA16Float, OutW, OutH, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite | MTLTextureUsageRenderTarget);
			X.S.colorTexture = Color; X.S.depthTexture = Depth; X.S.motionTexture = X.Motion; X.S.outputTexture = X.Out; X.S.exposureTexture = Expo;
			X.S.inputContentWidth = InW; X.S.inputContentHeight = InH; X.S.motionVectorScaleX = 1; X.S.motionVectorScaleY = 1; X.S.depthReversed = YES; X.S.preExposure = 1.0f;
			V.push_back(X);
		}
		id<MTLTexture> BilOut = MakeTex2D(Dev, MTLPixelFormatRGBA16Float, OutW, OutH, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite);

		printf("3D scene, input %dx%d -> output %dx%d (%d%%), %d frames\n", InW, InH, OutW, OutH, ScalePct, Frames);
		for (int F = 0; F < Frames; ++F)
		{
			Camera Cur = CameraAt(F), Prev = CameraAt(F > 0 ? F - 1 : 0);
			float Jx = Halton(F % 16 + 1, 2) - 0.5f, Jy = Halton(F % 16 + 1, 3) - 0.5f;
			E2EParams SP = MakeScene(Cur, InW, InH, HalfFov, MinZ, Jx, Jy, 1);
			Mat ProjCur = ReversedZPerspective(HalfFov, InW, InH, MinZ), ProjPrev = ProjCur;
			double PVTCur[3] = { -Cur.Pos[0], -Cur.Pos[1], -Cur.Pos[2] }, PVTPrev[3] = { -Prev.Pos[0], -Prev.Pos[1], -Prev.Pos[2] };
			Mat C2P = ClipToPrevClip(ProjCur, TranslatedViewMatrix(Cur), PVTCur, ProjPrev, TranslatedViewMatrix(Prev), PVTPrev);
			FParams KP{};
			for (int i = 0; i < 4; ++i) for (int j = 0; j < 4; ++j) KP.ClipToPrevClip[i * 4 + j] = (float)C2P.M[i][j];
			KP.ViewSize[0] = InW; KP.ViewSize[1] = InH; KP.VelocityExtent[0] = InW; KP.VelocityExtent[1] = InH;
			KP.ScreenToPixel[0] = InW * 0.5f; KP.ScreenToPixel[1] = InH * 0.5f; KP.ExposureFallback = 1.0f; KP.Flags = 0;
			RunCB(Q, ^(id<MTLCommandBuffer> CB) {
				id<MTLComputeCommandEncoder> E = [CB computeCommandEncoder];
				[E setComputePipelineState:PsoRender]; [E setTexture:Color atIndex:0]; [E setTexture:DepthR32 atIndex:1]; [E setBytes:&SP length:sizeof SP atIndex:0];
				Dispatch2D(E, PsoRender, InW, InH);
				[E setComputePipelineState:PsoZeroVel]; [E setTexture:Vel atIndex:0]; Dispatch2D(E, PsoZeroVel, InW, InH);
				[E endEncoding];
				MTLRenderPassDescriptor* RP = [MTLRenderPassDescriptor renderPassDescriptor];
				RP.depthAttachment.texture = Depth; RP.depthAttachment.loadAction = MTLLoadActionClear; RP.depthAttachment.storeAction = MTLStoreActionStore;
				RP.stencilAttachment.texture = Depth; RP.stencilAttachment.loadAction = MTLLoadActionClear; RP.stencilAttachment.storeAction = MTLStoreActionStore;
				id<MTLRenderCommandEncoder> R = [CB renderCommandEncoderWithDescriptor:RP];
				[R setRenderPipelineState:RPS]; [R setDepthStencilState:DSS]; [R setFragmentTexture:DepthR32 atIndex:0];
				[R drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];
				[R endEncoding];
				E = [CB computeCommandEncoder];
				[E setComputePipelineState:PsoMotion]; [E setTexture:Depth atIndex:0]; [E setTexture:Vel atIndex:1]; [E setTexture:MotionKernel atIndex:2]; [E setBytes:&KP length:sizeof KP atIndex:0];
				Dispatch2D(E, PsoMotion, InW, InH);
				[E setComputePipelineState:PsoExpo]; [E setTexture:Eye atIndex:0]; [E setTexture:Expo atIndex:1]; [E setBytes:&KP length:sizeof KP atIndex:0];
				[E dispatchThreadgroups:MTLSizeMake(1, 1, 1) threadsPerThreadgroup:MTLSizeMake(1, 1, 1)];
				[E setComputePipelineState:PsoNeg]; [E setTexture:MotionKernel atIndex:0]; [E setTexture:MotionNeg atIndex:1]; Dispatch2D(E, PsoNeg, InW, InH);
				[E setComputePipelineState:PsoZeroMot]; [E setTexture:MotionZero atIndex:0]; Dispatch2D(E, PsoZeroMot, InW, InH);
				simd_float2 CUV = { (float)InW / (float)InW, (float)InH / (float)InH };
				[E setComputePipelineState:PsoBil]; [E setTexture:Color atIndex:0]; [E setTexture:BilOut atIndex:1]; [E setBytes:&CUV length:8 atIndex:0]; Dispatch2D(E, PsoBil, OutW, OutH);
				[E endEncoding];
			});
			for (auto& X : V)
			{
				X.S.jitterOffsetX = Jx; X.S.jitterOffsetY = Jy; X.S.reset = (F == 0);
				RunCB(Q, ^(id<MTLCommandBuffer> CB) { [X.S encodeToCommandBuffer:CB]; });
			}
		}

		// Ground truth for the last frame: same camera, no jitter, 4x4 supersampling, output resolution.
		id<MTLTexture> GTc = MakeTex2D(Dev, MTLPixelFormatRGBA16Float, OutW, OutH, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite);
		id<MTLTexture> GTd = MakeTex2D(Dev, MTLPixelFormatR32Float, OutW, OutH, MTLTextureUsageShaderRead | MTLTextureUsageShaderWrite);
		E2EParams GP = MakeScene(CameraAt(Frames - 1), OutW, OutH, HalfFov, MinZ, 0, 0, 4);
		RunCB(Q, ^(id<MTLCommandBuffer> CB) {
			id<MTLComputeCommandEncoder> E = [CB computeCommandEncoder];
			[E setComputePipelineState:PsoRender]; [E setTexture:GTc atIndex:0]; [E setTexture:GTd atIndex:1]; [E setBytes:&GP length:sizeof GP atIndex:0];
			Dispatch2D(E, PsoRender, OutW, OutH);
			[E endEncoding];
		});
		auto ReadLuma = [&](id<MTLTexture> T, std::vector<float>& R) {
			id<MTLTexture> Sh = MakeTex2D(Dev, MTLPixelFormatRGBA16Float, OutW, OutH, MTLTextureUsageShaderRead, MTLStorageModeShared);
			RunCB(Q, ^(id<MTLCommandBuffer> CB) { id<MTLBlitCommandEncoder> B = [CB blitCommandEncoder]; [B copyFromTexture:T toTexture:Sh]; [B endEncoding]; });
			std::vector<_Float16> Raw((size_t)OutW * OutH * 4);
			[Sh getBytes:Raw.data() bytesPerRow:(size_t)OutW * 8 fromRegion:MTLRegionMake2D(0, 0, OutW, OutH) mipmapLevel:0];
			R.resize((size_t)OutW * OutH);
			for (size_t i = 0; i < R.size(); ++i) R[i] = 0.3f * (float)Raw[i * 4] + 0.6f * (float)Raw[i * 4 + 1] + 0.1f * (float)Raw[i * 4 + 2];
		};
		std::vector<float> GT, R;
		ReadLuma(GTc, GT);
		auto Psnr = [&](const std::vector<float>& A) {
			double Se = 0; size_t N = 0;
			for (int y = 40; y < OutH - 40; ++y) for (int x = 40; x < OutW - 40; ++x) { double D = (double)A[(size_t)y * OutW + x] - GT[(size_t)y * OutW + x]; Se += D * D; ++N; }
			return 10.0 * log10(1.0 / (Se / (double)N));
		};
		ReadLuma(BilOut, R); printf("%-44s : PSNR %.2f dB\n", "bilinear upscale of the last frame only", Psnr(R));
		for (auto& X : V) { ReadLuma(X.Out, R); printf("%-44s : PSNR %.2f dB\n", X.Label, Psnr(R)); }
	}
	return 0;
}
